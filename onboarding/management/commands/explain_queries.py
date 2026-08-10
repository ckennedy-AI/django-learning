from django.core.management.base import BaseCommand
from django.db.models import F

from onboarding.models import (
    ActivityEvent,
    ModuleAssignment,
    TaskAssignment,
    UserSkill,
)
from onboarding.selectors import skill_search


class Command(BaseCommand):
    """Run EXPLAIN ANALYZE over the access paths the endpoints actually filter on.

    The checklist says to add or adjust indexes based on the filters the
    endpoints use, then verify with EXPLAIN ANALYZE. Verify is the operative
    word: an index that exists is not the same as an index the planner chooses,
    and the only way to tell them apart is to read the plan. Run this against
    seeded data at volume, since on a handful of rows Postgres will pick a
    sequential scan no matter what indexes exist, and that plan tells you
    nothing.

    Read each plan for two things: whether it says Index Scan or Seq Scan, and
    whether the estimated row count is close to the actual. A wide gap between
    the two usually means stale statistics rather than a missing index.
    """

    help = "Print EXPLAIN ANALYZE plans for the queries behind each endpoint's filters."

    def add_arguments(self, parser):
        parser.add_argument(
            "--user-id",
            type=int,
            default=None,
            help="User to scope per-user queries to. Defaults to the first activity event's user.",
        )
        parser.add_argument(
            "--event-type",
            type=str,
            default=None,
            help="Event type to filter on. Defaults to the first one found.",
        )

    def handle(self, *args, **options):
        total_events = ActivityEvent.objects.count()

        if total_events < 1000:
            self.stdout.write(
                self.style.WARNING(
                    f"Only {total_events} ActivityEvent rows. Postgres will prefer a "
                    "sequential scan at this size regardless of indexes, so these plans "
                    "will not tell you much. Run seed_data --events 100000 first."
                )
            )

        user_id = (
            options["user_id"] or ActivityEvent.objects.values_list("user_id", flat=True).first()
        )
        event_type = (
            options["event_type"]
            or ActivityEvent.objects.values_list("event_type", flat=True).first()
        )

        if user_id is None:
            self.stdout.write(self.style.ERROR("No data. Run seed_data first."))
            return

        self.stdout.write(f"Rows in ActivityEvent: {total_events}")
        self.stdout.write(f"Scoping to user_id={user_id}, event_type={event_type}\n")

        # ActivityEventListApi, unfiltered feed. Ordering alone, no WHERE clause.
        self._explain(
            "ActivityEventListApi, no filter, ordered by the cursor field",
            ActivityEvent.objects.order_by("-occurred_at")[:20],
        )

        # ActivityEventListApi filtered by user. This is the case the composite
        # index activity_user_occurred_idx exists for: equality on user, then
        # ordering on occurred_at, which is exactly the index's column order.
        self._explain(
            "ActivityEventListApi, ?user_id= filter, ordered by the cursor field",
            ActivityEvent.objects.filter(user_id=user_id).order_by("-occurred_at")[:20],
        )

        # The same filter but ordered by id, which is what the endpoint used to
        # do. Kept here for contrast: no index covers (user, id), so this is the
        # plan that justified switching the cursor field to occurred_at.
        self._explain(
            "Contrast: same filter ordered by id instead, no index covers (user, id)",
            ActivityEvent.objects.filter(user_id=user_id).order_by("id")[:20],
        )

        # ActivityEventListApi filtered by event_type, which carries its own
        # db_index. Whether a composite (event_type, occurred_at) is worth adding
        # depends on this plan and on whether a sort shows up as a separate step.
        self._explain(
            "ActivityEventListApi, ?event_type= filter, ordered by the cursor field",
            ActivityEvent.objects.filter(event_type=event_type).order_by("-occurred_at")[:20],
        )

        # MyDashboardApi's two queries. Both are plain foreign key equality, which
        # Django already indexes, so these should be uncontroversial index scans.
        self._explain(
            "MyDashboardApi, module assignments by user",
            ModuleAssignment.objects.filter(user_id=user_id).values(
                "id", "status", "due_date", "completed_at", module_title=F("module__title")
            ),
        )
        self._explain(
            "MyDashboardApi, pending task assignments by assignee",
            TaskAssignment.objects.filter(assignee_id=user_id)
            .exclude(status=TaskAssignment.Status.APPROVED)
            .values("id", "status", task_title=F("task__title")),
        )

        # UserSkillsApi, the join through the explicit through model.
        self._explain(
            "UserSkillsApi, UserSkill by user with the skill joined in",
            UserSkill.objects.filter(user_id=user_id).select_related("skill"),
        )

        # TaskApprovalApi's scoped lookup. Filtering on assignee__manager_id means
        # joining User, so watch for whether the manager side uses its index.
        self._explain(
            "TaskApprovalApi, scoped lookup by assignee__manager_id",
            TaskAssignment.objects.select_related("assignee").filter(assignee__manager_id=user_id),
        )

        # SkillSearchApi. The one to check most carefully: pgvector will silently
        # fall back to a sequential scan if the query does not match the HNSW
        # index's operator class, and the results still look correct.
        # Calls the selector rather than restating its ordering, so this plan
        # cannot drift from the query the endpoint actually runs.
        #
        # A non-zero probe vector, deliberately. A zero vector has no direction,
        # so every cosine distance against it is NaN and an HNSW scan cannot be
        # navigated at all, which would make this plan describe a query no
        # caller ever sends. See caveat 16 in CLAUDE.md.
        self._explain(
            "SkillSearchApi, cosine distance ordering, should use the HNSW index",
            skill_search(embedding=[0.05] * 384, limit=10),
        )

    def _explain(self, label, queryset):
        self.stdout.write(self.style.SUCCESS(f"=== {label} ==="))

        try:
            plan = queryset.explain(analyze=True)
        except Exception as exc:
            # A failed EXPLAIN should not stop the rest of the plans from printing.
            self.stdout.write(self.style.ERROR(f"EXPLAIN failed: {exc}"))
        else:
            self.stdout.write(plan)

        self.stdout.write("")
