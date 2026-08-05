from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from onboarding.models import (
    ActivityEvent,
    Department,
    ModuleAssignment,
    OnboardingModule,
    OnboardingTask,
    Skill,
    TaskAssignment,
    User,
    UserSkill,
)


class EndpointQueryCountTests(TestCase):
    """Locks in the query counts recorded in CLAUDE.md's endpoint table.

    A failure here means either a regression (someone added an N+1) or a
    deliberate optimization change, in which case update both this count and
    the CLAUDE.md row together.
    """

    @classmethod
    def setUpTestData(cls):
        cls.department = Department.objects.create(name="Engineering")

        cls.manager = User.objects.create_user(
            username="manager", password="x", department=cls.department
        )
        cls.user = User.objects.create_user(
            username="employee", password="x", department=cls.department, manager=cls.manager
        )

        cls.module = OnboardingModule.objects.create(
            title="Code of Conduct",
            description="Company policy overview.",
            category=OnboardingModule.Category.POLICY,
            order=1,
        )
        ModuleAssignment.objects.create(
            user=cls.user,
            module=cls.module,
            due_date=timezone.now().date(),
            status=ModuleAssignment.Status.COMPLETED,
            completed_at=timezone.now(),
        )

        cls.task = OnboardingTask.objects.create(
            title="Set up laptop", description="IT provisioning."
        )
        cls.task_assignment = TaskAssignment.objects.create(
            task=cls.task, assignee=cls.user, status=TaskAssignment.Status.COMPLETED
        )

        cls.skill = Skill.objects.create(
            name="Django ORM", description="Query optimization.", embedding=[0.0] * 384
        )
        UserSkill.objects.create(user=cls.user, skill=cls.skill)

        ActivityEvent.objects.create(user=cls.user, event_type="login", occurred_at=timezone.now())

    def setUp(self):
        cache.clear()

    def test_module_list_is_two_queries(self):
        # LimitOffsetPagination costs a COUNT on top of the page query. That is
        # the price of an unbounded list becoming bounded, and it is worth it
        # here: without it the endpoint would serialize every module in the
        # catalogue on every call.
        with self.assertNumQueries(2):
            response = self.client.get(reverse("module-list"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("results", response.data)
        self.assertEqual(response.data["count"], 1)

    def test_module_detail_is_one_query(self):
        with self.assertNumQueries(1):
            response = self.client.get(reverse("module-detail", args=[self.module.id]))
        self.assertEqual(response.status_code, 200)

    def test_activity_event_list_is_one_query(self):
        # Cursor pagination has no COUNT, which is half the reason it stays at one
        # query no matter how deep the page.
        with self.assertNumQueries(1):
            response = self.client.get(reverse("activity-event-list"))
        self.assertEqual(response.status_code, 200)

    def test_activity_event_list_filtered_by_user_is_one_query(self):
        with self.assertNumQueries(1):
            response = self.client.get(reverse("activity-event-list"), {"user_id": self.user.id})
        self.assertEqual(response.status_code, 200)

    def test_activity_event_list_pages_through_the_occurred_at_cursor(self):
        # The cursor field is occurred_at, a datetime, not an integer id. This
        # walks the whole feed through the next links to prove the datetime
        # round-trips through the opaque cursor without dropping or repeating a
        # row, which is the failure mode a non-unique or coarse cursor field
        # produces.
        now = timezone.now()
        for index in range(25):
            ActivityEvent.objects.create(
                user=self.user,
                event_type="page_view",
                occurred_at=now - timedelta(seconds=index),
            )

        seen_ids = []
        occurred_at_values = []
        url = reverse("activity-event-list")

        while url:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            for row in response.data["results"]:
                seen_ids.append(row["id"])
                occurred_at_values.append(row["occurred_at"])
            url = response.data["next"]

        total = ActivityEvent.objects.count()
        self.assertEqual(len(seen_ids), total)
        self.assertEqual(len(set(seen_ids)), total, "cursor paging repeated a row")
        self.assertEqual(
            occurred_at_values,
            sorted(occurred_at_values, reverse=True),
            "feed is not in descending occurred_at order",
        )

    def test_user_detail_is_one_query(self):
        with self.assertNumQueries(1):
            response = self.client.get(reverse("user-detail", args=[self.user.id]))
        self.assertEqual(response.status_code, 200)

    def test_user_skills_is_two_queries(self):
        # One COUNT from the paginator, one page query with the skill joined in.
        # The number that matters is that it does not grow with the number of
        # skills, which is what select_related buys. See
        # `manage.py benchmark_user_skills` for the measured comparison.
        with self.assertNumQueries(2):
            response = self.client.get(reverse("user-skills", args=[self.user.id]))
        self.assertEqual(response.status_code, 200)
        self.assertIn("results", response.data)

    def test_user_skills_query_count_does_not_grow_with_skills(self):
        # The N+1 guard. Adding skills must not add queries, otherwise the
        # select_related in the selector has been lost.
        for index in range(5):
            skill = Skill.objects.create(
                name=f"Skill {index}", description="Extra.", embedding=[0.0] * 384
            )
            UserSkill.objects.create(user=self.user, skill=skill)

        with self.assertNumQueries(2):
            response = self.client.get(reverse("user-skills", args=[self.user.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 6)

    def test_user_reports_is_two_queries(self):
        # select_related("manager") and prefetch_related("direct_reports") can't
        # collapse into one query, a JOIN can't flatten a reverse FK into a list.
        with self.assertNumQueries(2):
            response = self.client.get(reverse("user-reports", args=[self.manager.id]))
        self.assertEqual(response.status_code, 200)

    def test_department_activity_report_scales_with_department_count(self):
        # Deliberately unoptimized: one query per department for headcount, total
        # assignments, completed assignments, and activity event count.
        department_count = Department.objects.count()
        with self.assertNumQueries(1 + 4 * department_count):
            response = self.client.get(reverse("department-activity-report"))
        self.assertEqual(response.status_code, 200)

    @patch("onboarding.views.embed_texts")
    def test_skill_search_is_one_query(self, mock_embed_texts):
        mock_embed_texts.return_value = [[0.0] * 384]
        with self.assertNumQueries(1):
            response = self.client.get(reverse("skill-search"), {"q": "orm"})
        self.assertEqual(response.status_code, 200)

    def test_dashboard_is_two_queries_on_miss_zero_on_hit(self):
        with self.assertNumQueries(2):
            response = self.client.get(reverse("my-dashboard"), {"user_id": self.user.id})
        self.assertEqual(response.status_code, 200)

        with self.assertNumQueries(0):
            response = self.client.get(reverse("my-dashboard"), {"user_id": self.user.id})
        self.assertEqual(response.status_code, 200)

    def test_task_approval_invalidates_dashboard_cache(self):
        # Warm the assignee's dashboard cache first.
        self.client.get(reverse("my-dashboard"), {"user_id": self.user.id})
        cache_key = f"onboarding:user_dashboard:{self.user.id}"
        self.assertIsNotNone(cache.get(cache_key))

        # TestCase rolls back its transaction, so on_commit callbacks never fire
        # unless captured and executed explicitly.
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse("task-assignment-approve", args=[self.task_assignment.id]),
                data={"manager_id": self.manager.id},
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(cache.get(cache_key))

    def test_task_approval_rejects_other_managers(self):
        other_manager = User.objects.create_user(username="other_manager", password="x")

        response = self.client.post(
            reverse("task-assignment-approve", args=[self.task_assignment.id]),
            data={"manager_id": other_manager.id},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 404)


class InvalidInputTests(TestCase):
    """Locks in the invalid-input policy documented in CLAUDE.md.

    The decision is 4xx rather than a safe default: a missing or malformed
    parameter is a client bug, and silently substituting a default would return
    a plausible-looking response for a question the caller did not ask. The one
    exception is a serializer field that declares a default, which is a
    documented part of the contract rather than a guess.
    """

    def test_missing_required_filter_is_400_not_a_default(self):
        response = self.client.get(reverse("my-dashboard"))

        self.assertEqual(response.status_code, 400)
        self.assertIn("user_id", response.data["extra"]["fields"])

    def test_malformed_filter_is_400(self):
        response = self.client.get(reverse("my-dashboard"), {"user_id": "not-an-integer"})

        self.assertEqual(response.status_code, 400)

    def test_limit_above_the_upper_bound_is_rejected(self):
        # The upper bound on a limit parameter is enforced, not clamped, so a
        # caller asking for 5,000 rows learns that it was refused.
        response = self.client.get(reverse("skill-search"), {"q": "orm", "limit": 5000})

        self.assertEqual(response.status_code, 400)
        self.assertIn("limit", response.data["extra"]["fields"])

    def test_pagination_limit_above_max_clamps_rather_than_erroring(self):
        # DRF's own paginator clamps to max_limit instead of erroring. Noting the
        # inconsistency with the serializer-validated limit above deliberately:
        # this one is DRF's behaviour, not a choice this project made.
        response = self.client.get(reverse("module-list"), {"limit": 5000})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["limit"], 50)

    def test_error_responses_share_one_shape(self):
        response = self.client.get(reverse("my-dashboard"))

        self.assertIn("message", response.data)
        self.assertIn("extra", response.data)

    def test_unknown_id_is_404_in_the_same_shape(self):
        response = self.client.get(reverse("module-detail", args=[999999]))

        self.assertEqual(response.status_code, 404)
        self.assertIn("message", response.data)
        self.assertIn("extra", response.data)
