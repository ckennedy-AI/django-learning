from datetime import date, timedelta

from django.http import Http404
from django.test import TestCase
from django.utils import timezone

from onboarding.models import ModuleAssignment
from onboarding.selectors import (
    module_assignment_overdue_user_list,
    module_get,
    module_list,
)
from onboarding.selectors.modules import OVERDUE_REMINDER_EVENT_TYPE
from onboarding.tests.factories import (
    ActivityEventFactory,
    ModuleAssignmentFactory,
    OnboardingModuleFactory,
    UserFactory,
)


class ModuleListTests(TestCase):
    def test_returns_all_modules(self):
        OnboardingModuleFactory.create_batch(3)

        result = list(module_list())

        self.assertEqual(len(result), 3)

    def test_returns_empty_when_no_modules(self):
        result = list(module_list())

        self.assertEqual(len(result), 0)


class ModuleGetTests(TestCase):
    def test_returns_the_right_module(self):
        module = OnboardingModuleFactory(title="Onboarding 101")

        result = module_get(module_id=module.id)

        self.assertEqual(result.id, module.id)
        self.assertEqual(result.title, "Onboarding 101")

    def test_raises_http404_for_unknown_id(self):
        with self.assertRaises(Http404):
            module_get(module_id=99999)


class ModuleAssignmentOverdueUserListTests(TestCase):
    def test_includes_user_with_overdue_incomplete_assignment(self):
        today = date.today()
        past_date = today - timedelta(days=1)
        user = UserFactory(email="user@example.com", is_active=True)
        module = OnboardingModuleFactory()

        ModuleAssignmentFactory(
            user=user,
            module=module,
            due_date=past_date,
            status=ModuleAssignment.Status.NOT_STARTED,
            completed_at=None,
        )

        result = list(
            module_assignment_overdue_user_list(
                as_of=today, reminded_since=timezone.now() - timedelta(days=1)
            )
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].id, user.id)

    def test_excludes_user_with_no_overdue_assignments(self):
        today = date.today()
        future_date = today + timedelta(days=1)
        user = UserFactory(email="user@example.com", is_active=True)
        module = OnboardingModuleFactory()

        ModuleAssignmentFactory(
            user=user,
            module=module,
            due_date=future_date,
            status=ModuleAssignment.Status.NOT_STARTED,
            completed_at=None,
        )

        result = list(
            module_assignment_overdue_user_list(
                as_of=today, reminded_since=timezone.now() - timedelta(days=1)
            )
        )

        self.assertEqual(len(result), 0)

    def test_excludes_completed_assignments(self):
        today = date.today()
        past_date = today - timedelta(days=1)
        user = UserFactory(email="user@example.com", is_active=True)
        module = OnboardingModuleFactory()

        ModuleAssignmentFactory(
            user=user,
            module=module,
            due_date=past_date,
            status=ModuleAssignment.Status.COMPLETED,
            completed_at=timezone.now(),
        )

        result = list(
            module_assignment_overdue_user_list(
                as_of=today, reminded_since=timezone.now() - timedelta(days=1)
            )
        )

        self.assertEqual(len(result), 0)

    def test_excludes_user_with_blank_email(self):
        today = date.today()
        past_date = today - timedelta(days=1)
        user = UserFactory(email="", is_active=True)
        module = OnboardingModuleFactory()

        ModuleAssignmentFactory(
            user=user,
            module=module,
            due_date=past_date,
            status=ModuleAssignment.Status.NOT_STARTED,
            completed_at=None,
        )

        result = list(
            module_assignment_overdue_user_list(
                as_of=today, reminded_since=timezone.now() - timedelta(days=1)
            )
        )

        self.assertEqual(len(result), 0)

    def test_excludes_inactive_users(self):
        today = date.today()
        past_date = today - timedelta(days=1)
        user = UserFactory(email="user@example.com", is_active=False)
        module = OnboardingModuleFactory()

        ModuleAssignmentFactory(
            user=user,
            module=module,
            due_date=past_date,
            status=ModuleAssignment.Status.NOT_STARTED,
            completed_at=None,
        )

        result = list(
            module_assignment_overdue_user_list(
                as_of=today, reminded_since=timezone.now() - timedelta(days=1)
            )
        )

        self.assertEqual(len(result), 0)

    def test_excludes_user_already_reminded_since(self):
        today = date.today()
        past_date = today - timedelta(days=1)
        user = UserFactory(email="user@example.com", is_active=True)
        module = OnboardingModuleFactory()

        ModuleAssignmentFactory(
            user=user,
            module=module,
            due_date=past_date,
            status=ModuleAssignment.Status.NOT_STARTED,
            completed_at=None,
        )

        reminder_cutoff = timezone.now() - timedelta(hours=12)
        ActivityEventFactory(
            user=user, event_type=OVERDUE_REMINDER_EVENT_TYPE, occurred_at=timezone.now()
        )

        result = list(
            module_assignment_overdue_user_list(as_of=today, reminded_since=reminder_cutoff)
        )

        self.assertEqual(len(result), 0)

    def test_includes_user_not_reminded_since_cutoff(self):
        today = date.today()
        past_date = today - timedelta(days=1)
        user = UserFactory(email="user@example.com", is_active=True)
        module = OnboardingModuleFactory()

        ModuleAssignmentFactory(
            user=user,
            module=module,
            due_date=past_date,
            status=ModuleAssignment.Status.NOT_STARTED,
            completed_at=None,
        )

        # Reminder was sent before the cutoff
        reminder_cutoff = timezone.now() - timedelta(hours=12)
        old_reminder = timezone.now() - timedelta(days=1)
        ActivityEventFactory(
            user=user, event_type=OVERDUE_REMINDER_EVENT_TYPE, occurred_at=old_reminder
        )

        result = list(
            module_assignment_overdue_user_list(as_of=today, reminded_since=reminder_cutoff)
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].id, user.id)

    def test_returns_users_in_id_order(self):
        today = date.today()
        past_date = today - timedelta(days=1)
        module = OnboardingModuleFactory()
        reminder_cutoff = timezone.now() - timedelta(hours=12)

        # Create users in reverse order to ensure ordering actually works
        users = []
        for _ in range(3):
            user = UserFactory(email="user@example.com", is_active=True)
            users.append(user)
            ModuleAssignmentFactory(
                user=user,
                module=module,
                due_date=past_date,
                status=ModuleAssignment.Status.NOT_STARTED,
                completed_at=None,
            )

        result = list(
            module_assignment_overdue_user_list(as_of=today, reminded_since=reminder_cutoff)
        )

        result_ids = [r.id for r in result]
        expected_ids = sorted([u.id for u in users])
        self.assertEqual(result_ids, expected_ids)

    def test_includes_user_with_multiple_overdue_assignments(self):
        today = date.today()
        past_date = today - timedelta(days=1)
        user = UserFactory(email="user@example.com", is_active=True)
        module1 = OnboardingModuleFactory()
        module2 = OnboardingModuleFactory()

        ModuleAssignmentFactory(
            user=user,
            module=module1,
            due_date=past_date,
            status=ModuleAssignment.Status.NOT_STARTED,
            completed_at=None,
        )
        ModuleAssignmentFactory(
            user=user,
            module=module2,
            due_date=past_date,
            status=ModuleAssignment.Status.NOT_STARTED,
            completed_at=None,
        )

        result = list(
            module_assignment_overdue_user_list(
                as_of=today, reminded_since=timezone.now() - timedelta(days=1)
            )
        )

        # User should appear once, not twice
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].id, user.id)
