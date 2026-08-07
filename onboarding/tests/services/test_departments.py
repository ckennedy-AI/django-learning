from datetime import date

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from onboarding.models import (
    ActivityEvent,
    Department,
    DepartmentProgressSnapshot,
    ModuleAssignment,
    OnboardingModule,
    User,
)
from onboarding.services import department_progress_rollup


class DepartmentProgressRollupTests(TestCase):
    """The unique-constraint idempotency exercise, the counterpart to scoring."""

    def setUp(self):
        self.captured_on = date(2026, 8, 7)
        self.engineering = Department.objects.create(name="Engineering")
        self.sales = Department.objects.create(name="Sales")

        self.module = OnboardingModule.objects.create(
            title="Culture",
            description="How we work.",
            category=OnboardingModule.Category.CULTURE,
        )

        self.dev = User.objects.create_user(
            username="dev", password="x", department=self.engineering
        )
        ModuleAssignment.objects.create(
            user=self.dev,
            module=self.module,
            due_date=self.captured_on,
            status=ModuleAssignment.Status.COMPLETED,
            completed_at=timezone.now(),
        )
        ActivityEvent.objects.create(user=self.dev, event_type="module_completed")

    def test_writes_one_snapshot_per_department(self):
        result = department_progress_rollup(captured_on=self.captured_on)

        self.assertEqual(result, {"captured_on": "2026-08-07", "departments": 2})
        self.assertEqual(DepartmentProgressSnapshot.objects.count(), 2)

    def test_the_snapshot_matches_the_live_report(self):
        """The rollup reuses the report selector, so the numbers cannot drift."""
        department_progress_rollup(captured_on=self.captured_on)

        snapshot = DepartmentProgressSnapshot.objects.get(department=self.engineering)
        self.assertEqual(snapshot.employee_count, 1)
        self.assertEqual(snapshot.completion_percentage, 100.0)
        self.assertEqual(snapshot.activity_event_count, 1)

    def test_an_empty_department_gets_a_zeroed_row(self):
        """A department with nothing to report still gets a row.

        A missing row and a row of zeroes read very differently later: one says
        "no data", the other says "no progress".
        """
        department_progress_rollup(captured_on=self.captured_on)

        snapshot = DepartmentProgressSnapshot.objects.get(department=self.sales)
        self.assertEqual(snapshot.employee_count, 0)
        self.assertEqual(snapshot.completion_percentage, 0.0)

    def test_running_twice_updates_rather_than_duplicates(self):
        department_progress_rollup(captured_on=self.captured_on)
        first_ids = set(DepartmentProgressSnapshot.objects.values_list("id", flat=True))

        department_progress_rollup(captured_on=self.captured_on)

        self.assertEqual(DepartmentProgressSnapshot.objects.count(), 2)
        # The same rows, updated in place. New ids would mean the old ones were
        # deleted and reinserted, which is a different and worse kind of
        # idempotent.
        self.assertEqual(
            set(DepartmentProgressSnapshot.objects.values_list("id", flat=True)), first_ids
        )

    def test_a_rerun_picks_up_changed_numbers(self):
        department_progress_rollup(captured_on=self.captured_on)

        User.objects.create_user(username="dev2", password="x", department=self.engineering)
        department_progress_rollup(captured_on=self.captured_on)

        snapshot = DepartmentProgressSnapshot.objects.get(department=self.engineering)
        self.assertEqual(snapshot.employee_count, 2)

    def test_a_different_date_is_a_different_row(self):
        department_progress_rollup(captured_on=self.captured_on)
        department_progress_rollup(captured_on=date(2026, 8, 8))

        self.assertEqual(DepartmentProgressSnapshot.objects.count(), 4)
        self.assertEqual(
            DepartmentProgressSnapshot.objects.filter(department=self.engineering).count(), 2
        )

    def test_the_database_rejects_a_second_row_for_the_same_day(self):
        """The constraint is the idempotency, so it gets its own test.

        `update_or_create` is check-then-write and cannot be trusted on its own
        under concurrency. This asserts the thing that actually holds: Postgres
        refuses the duplicate, which is what turns a lost race into a caught
        IntegrityError instead of a second row.
        """
        department_progress_rollup(captured_on=self.captured_on)

        with self.assertRaises(IntegrityError):
            # atomic() so the broken transaction is contained and the rest of the
            # test case can still talk to the database.
            with transaction.atomic():
                DepartmentProgressSnapshot.objects.create(
                    department=self.engineering,
                    captured_on=self.captured_on,
                    employee_count=99,
                    completion_percentage=0.0,
                    activity_event_count=0,
                )

    def test_defaults_captured_on_to_today(self):
        result = department_progress_rollup()

        self.assertEqual(result["captured_on"], timezone.localdate().isoformat())
        self.assertTrue(
            DepartmentProgressSnapshot.objects.filter(captured_on=timezone.localdate()).exists()
        )
