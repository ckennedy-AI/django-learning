import time

from django.core.management.base import BaseCommand
from django.db import connection
from django.db.models import Count
from django.test.utils import CaptureQueriesContext

from onboarding.models import User, UserSkill
from onboarding.selectors import user_skills_list


class Command(BaseCommand):
    """Measure the cost of the user-to-skill read before trusting it in an endpoint.

    UserSkillsApi exposes a relationship that goes through an explicit join
    table, which is exactly the shape that hides an N+1. The rule in CLAUDE.md
    is to measure a many-to-many read rather than assume the optimization
    helped, so this command runs the three shapes side by side and reports both
    the query count and the wall time.

    Worth being precise about the relationship: User has no ManyToManyField to
    Skill. UserSkill is a plain model with two foreign keys, so what looks like
    a many-to-many read is really a reverse foreign key from User to UserSkill
    followed by a forward foreign key from UserSkill to Skill. That second hop
    is where the N+1 comes from, and it is what select_related collapses.
    """

    help = "Compare the UserSkill read with no select_related, with select_related, and prefetched."

    def add_arguments(self, parser):
        parser.add_argument(
            "--user-id",
            type=int,
            default=None,
            help="Defaults to the user with the most skills, the worst case for an N+1.",
        )

    def handle(self, *args, **options):
        user_id = options["user_id"]

        if user_id is None:
            user_id = (
                User.objects.annotate(skill_count=Count("skills"))
                .order_by("-skill_count")
                .values_list("id", flat=True)
                .first()
            )

        if user_id is None:
            self.stdout.write(self.style.ERROR("No users. Run seed_data first."))
            return

        skill_count = UserSkill.objects.filter(user_id=user_id).count()

        if skill_count == 0:
            self.stdout.write(
                self.style.ERROR(f"user_id {user_id} has no skills, nothing to measure.")
            )
            return

        self.stdout.write(f"user_id: {user_id}, skills: {skill_count}")

        # Shape 1: the naive read. One query for the UserSkill rows, then one
        # more per row the moment the serializer touches skill.name. This is the
        # N+1 the endpoint has to avoid, measured rather than asserted.
        naive_queries, naive_duration = self._measure(
            lambda: [us.skill.name for us in UserSkill.objects.filter(user_id=user_id)]
        )

        # Shape 2: what user_skills_list actually ships. The JOIN pulls the skill
        # row in alongside the UserSkill row, so the second hop costs nothing.
        shipped_queries, shipped_duration = self._measure(
            lambda: [us.skill.name for us in user_skills_list(user_id=user_id)]
        )

        # Shape 3: prefetch_related instead. Correct, and immune to the N+1, but
        # it deliberately issues a second query to fetch the skills separately.
        # For a forward foreign key that is a worse trade than the JOIN.
        prefetch_queries, prefetch_duration = self._measure(
            lambda: [
                us.skill.name
                for us in UserSkill.objects.filter(user_id=user_id).prefetch_related("skill")
            ]
        )

        self._report("No select_related (N+1)", naive_queries, naive_duration)
        self._report("select_related, as shipped", shipped_queries, shipped_duration)
        self._report("prefetch_related", prefetch_queries, prefetch_duration)

        if shipped_duration > 0:
            self.stdout.write(
                f"select_related versus N+1: {naive_duration / shipped_duration:.1f}x "
                f"faster, {naive_queries - shipped_queries} fewer queries"
            )

    def _measure(self, read):
        with CaptureQueriesContext(connection) as captured:
            start = time.perf_counter()
            read()
            duration = time.perf_counter() - start

        return len(captured), duration

    def _report(self, label, queries, duration):
        self.stdout.write(
            self.style.SUCCESS(f"{label}: {queries} queries, {duration * 1000:.2f} ms")
        )
