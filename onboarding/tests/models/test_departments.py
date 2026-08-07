from datetime import date

from django.db import IntegrityError, transaction
from django.test import TestCase

from onboarding.tests.factories import DepartmentFactory, DepartmentProgressSnapshotFactory


class DepartmentProgressSnapshotUniquenessTests(TestCase):
    """The constraint is what makes the nightly rollup idempotent under concurrency.

    The unique constraint on (department, captured_on) turns a lost race in the
    check-then-write of update_or_create into an IntegrityError caught by the
    service, rather than a silent duplicate row. Without it, two schedulers or
    reruns landing at the same time would both pass the check and both write.
    """

    def test_a_second_row_for_the_same_department_and_date_raises_integrity_error(self):
        snapshot = DepartmentProgressSnapshotFactory(
            captured_on=date(2026, 8, 7),
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                DepartmentProgressSnapshotFactory(
                    department=snapshot.department,
                    captured_on=snapshot.captured_on,
                )

    def test_a_second_row_for_the_same_department_but_different_date_succeeds(self):
        snapshot = DepartmentProgressSnapshotFactory(
            captured_on=date(2026, 8, 7),
        )

        new_snapshot = DepartmentProgressSnapshotFactory(
            department=snapshot.department,
            captured_on=date(2026, 8, 8),
        )

        self.assertIsNotNone(new_snapshot.id)

    def test_a_second_row_for_the_same_date_but_different_department_succeeds(self):
        department1 = DepartmentFactory()
        department2 = DepartmentFactory()
        DepartmentProgressSnapshotFactory(
            department=department1,
            captured_on=date(2026, 8, 7),
        )

        snapshot2 = DepartmentProgressSnapshotFactory(
            department=department2,
            captured_on=date(2026, 8, 7),
        )

        self.assertIsNotNone(snapshot2.id)
