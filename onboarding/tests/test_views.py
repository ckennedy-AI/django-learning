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

    def test_module_list_is_one_query(self):
        with self.assertNumQueries(1):
            response = self.client.get(reverse("module-list"))
        self.assertEqual(response.status_code, 200)

    def test_module_detail_is_one_query(self):
        with self.assertNumQueries(1):
            response = self.client.get(reverse("module-detail", args=[self.module.id]))
        self.assertEqual(response.status_code, 200)

    def test_activity_event_list_is_one_query(self):
        with self.assertNumQueries(1):
            response = self.client.get(reverse("activity-event-list"))
        self.assertEqual(response.status_code, 200)

    def test_user_detail_is_one_query(self):
        with self.assertNumQueries(1):
            response = self.client.get(reverse("user-detail", args=[self.user.id]))
        self.assertEqual(response.status_code, 200)

    def test_user_skills_is_one_query(self):
        with self.assertNumQueries(1):
            response = self.client.get(reverse("user-skills", args=[self.user.id]))
        self.assertEqual(response.status_code, 200)

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
