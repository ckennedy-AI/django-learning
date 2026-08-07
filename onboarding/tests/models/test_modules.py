from datetime import date, timedelta

from django.test import TestCase
from django.utils import timezone

from onboarding.tests.factories import ModuleAssignmentFactory


class ModuleAssignmentQuerySetIncompleteTests(TestCase):
    """The incomplete queryset excludes only the COMPLETED status."""

    def test_excludes_completed_assignments(self):
        ModuleAssignmentFactory(status="not_started")
        ModuleAssignmentFactory(status="in_progress")
        completed = ModuleAssignmentFactory(status="completed")

        incomplete = ModuleAssignmentFactory._meta.model.objects.incomplete()

        self.assertNotIn(completed, incomplete)
        self.assertEqual(incomplete.count(), 2)

    def test_includes_all_non_completed_statuses(self):
        not_started = ModuleAssignmentFactory(status="not_started")
        in_progress = ModuleAssignmentFactory(status="in_progress")
        ModuleAssignmentFactory(status="completed")

        incomplete = ModuleAssignmentFactory._meta.model.objects.incomplete()

        self.assertCountEqual(list(incomplete), [not_started, in_progress])


class ModuleAssignmentIsOverdueTests(TestCase):
    """The is_overdue property accounts for completion and date comparison."""

    def test_completed_assignment_is_never_overdue_regardless_of_due_date(self):
        past_date = date.today() - timedelta(days=365)
        assignment = ModuleAssignmentFactory(
            status="completed",
            due_date=past_date,
            completed_at=timezone.now(),
        )

        self.assertFalse(assignment.is_overdue)

    def test_incomplete_assignment_with_past_due_date_is_overdue(self):
        past_date = date.today() - timedelta(days=1)
        assignment = ModuleAssignmentFactory(
            status="not_started",
            due_date=past_date,
            completed_at=None,
        )

        self.assertTrue(assignment.is_overdue)

    def test_incomplete_assignment_with_today_as_due_date_is_not_overdue(self):
        assignment = ModuleAssignmentFactory(
            status="in_progress",
            due_date=date.today(),
            completed_at=None,
        )

        self.assertFalse(assignment.is_overdue)

    def test_incomplete_assignment_with_future_due_date_is_not_overdue(self):
        future_date = date.today() + timedelta(days=1)
        assignment = ModuleAssignmentFactory(
            status="not_started",
            due_date=future_date,
            completed_at=None,
        )

        self.assertFalse(assignment.is_overdue)
