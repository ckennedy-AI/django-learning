from datetime import date, timedelta

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from onboarding.models import ModuleAssignment, TaskAssignment
from onboarding.selectors import user_dashboard_cache_invalidate, user_dashboard_get
from onboarding.tests.factories import (
    ModuleAssignmentFactory,
    OnboardingModuleFactory,
    TaskAssignmentFactory,
    UserFactory,
)


class UserDashboardGetTests(TestCase):
    def setUp(self):
        super().setUp()
        cache.clear()

    def test_returns_correct_shape(self):
        user = UserFactory()
        module = OnboardingModuleFactory()
        ModuleAssignmentFactory(
            user=user,
            module=module,
            status=ModuleAssignment.Status.NOT_STARTED,
            due_date=date.today(),
        )
        TaskAssignmentFactory(assignee=user, status=TaskAssignment.Status.PENDING)

        result = user_dashboard_get(user_id=user.id)

        self.assertIn("module_assignments", result)
        self.assertIn("pending_tasks", result)
        self.assertIn("completion_percentage", result)

    def test_module_assignments_include_required_fields(self):
        user = UserFactory()
        module = OnboardingModuleFactory(title="Onboarding")
        ModuleAssignmentFactory(
            user=user,
            module=module,
            status=ModuleAssignment.Status.NOT_STARTED,
            due_date=date.today(),
        )

        result = user_dashboard_get(user_id=user.id)

        assignment = result["module_assignments"][0]
        self.assertIn("id", assignment)
        self.assertIn("status", assignment)
        self.assertIn("due_date", assignment)
        self.assertIn("completed_at", assignment)
        self.assertIn("module_title", assignment)
        self.assertIn("is_overdue", assignment)

    def test_marks_overdue_incomplete_assignments(self):
        user = UserFactory()
        module = OnboardingModuleFactory()
        past_date = date.today() - timedelta(days=1)
        ModuleAssignmentFactory(
            user=user,
            module=module,
            status=ModuleAssignment.Status.NOT_STARTED,
            due_date=past_date,
            completed_at=None,
        )

        result = user_dashboard_get(user_id=user.id)

        assignment = result["module_assignments"][0]
        self.assertTrue(assignment["is_overdue"])

    def test_marks_not_overdue_when_completed(self):
        user = UserFactory()
        module = OnboardingModuleFactory()
        past_date = date.today() - timedelta(days=1)
        ModuleAssignmentFactory(
            user=user,
            module=module,
            status=ModuleAssignment.Status.COMPLETED,
            due_date=past_date,
            completed_at=timezone.now(),
        )

        result = user_dashboard_get(user_id=user.id)

        assignment = result["module_assignments"][0]
        self.assertFalse(assignment["is_overdue"])

    def test_pending_tasks_include_required_fields(self):
        user = UserFactory()
        TaskAssignmentFactory(assignee=user, status=TaskAssignment.Status.PENDING)

        result = user_dashboard_get(user_id=user.id)

        pending = result["pending_tasks"][0]
        self.assertIn("id", pending)
        self.assertIn("status", pending)
        self.assertIn("task_title", pending)

    def test_excludes_approved_tasks(self):
        user = UserFactory()
        TaskAssignmentFactory(assignee=user, status=TaskAssignment.Status.PENDING)
        TaskAssignmentFactory(assignee=user, status=TaskAssignment.Status.APPROVED)

        result = user_dashboard_get(user_id=user.id)

        self.assertEqual(len(result["pending_tasks"]), 1)

    def test_completion_percentage_correct(self):
        user = UserFactory()
        module1 = OnboardingModuleFactory()
        module2 = OnboardingModuleFactory()

        ModuleAssignmentFactory(user=user, module=module1, status=ModuleAssignment.Status.COMPLETED)
        ModuleAssignmentFactory(
            user=user, module=module2, status=ModuleAssignment.Status.NOT_STARTED
        )

        result = user_dashboard_get(user_id=user.id)

        self.assertEqual(result["completion_percentage"], 50.0)

    def test_completion_percentage_zero_when_no_modules(self):
        user = UserFactory()

        result = user_dashboard_get(user_id=user.id)

        self.assertEqual(result["completion_percentage"], 0.0)

    def test_is_two_queries_on_cache_miss(self):
        user = UserFactory()
        ModuleAssignmentFactory(user=user)

        with self.assertNumQueries(2):
            user_dashboard_get(user_id=user.id)

    def test_is_zero_queries_on_cache_hit(self):
        user = UserFactory()
        ModuleAssignmentFactory(user=user)

        user_dashboard_get(user_id=user.id)

        with self.assertNumQueries(0):
            user_dashboard_get(user_id=user.id)

    def test_returns_same_value_on_cache_hit(self):
        user = UserFactory()
        module = OnboardingModuleFactory()
        ModuleAssignmentFactory(
            user=user,
            module=module,
            status=ModuleAssignment.Status.NOT_STARTED,
            due_date=date.today(),
        )

        result1 = user_dashboard_get(user_id=user.id)
        result2 = user_dashboard_get(user_id=user.id)

        self.assertEqual(result1, result2)
        self.assertEqual(result1["module_assignments"][0]["module_title"], module.title)


class UserDashboardCacheInvalidateTests(TestCase):
    def setUp(self):
        super().setUp()
        cache.clear()

    def test_invalidates_cached_dashboard(self):
        user = UserFactory()
        ModuleAssignmentFactory(user=user)

        user_dashboard_get(user_id=user.id)
        user_dashboard_cache_invalidate(user_id=user.id)

        with self.assertNumQueries(2):
            user_dashboard_get(user_id=user.id)

    def test_invalidate_only_affects_target_user(self):
        user1 = UserFactory()
        user2 = UserFactory()
        ModuleAssignmentFactory(user=user1)
        ModuleAssignmentFactory(user=user2)

        user_dashboard_get(user_id=user1.id)
        user_dashboard_get(user_id=user2.id)

        user_dashboard_cache_invalidate(user_id=user1.id)

        with self.assertNumQueries(2):
            user_dashboard_get(user_id=user1.id)

        with self.assertNumQueries(0):
            user_dashboard_get(user_id=user2.id)
