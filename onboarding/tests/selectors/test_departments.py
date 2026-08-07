from django.test import TestCase

from onboarding.models import ModuleAssignment
from onboarding.selectors import department_activity_report_list
from onboarding.tests.factories import (
    ActivityEventFactory,
    DepartmentFactory,
    ModuleAssignmentFactory,
    OnboardingModuleFactory,
    UserFactory,
)


class DepartmentActivityReportListTests(TestCase):
    def test_returns_one_row_per_department(self):
        DepartmentFactory(name="Engineering")
        DepartmentFactory(name="Sales")

        result = department_activity_report_list()

        self.assertEqual(len(result), 2)
        dept_names = {row["department_name"] for row in result}
        self.assertEqual(dept_names, {"Engineering", "Sales"})

    def test_reports_correct_employee_count(self):
        dept = DepartmentFactory()
        UserFactory(department=dept)
        UserFactory(department=dept)
        UserFactory(department=dept)

        result = department_activity_report_list()

        row = next(r for r in result if r["department_id"] == dept.id)
        self.assertEqual(row["employee_count"], 3)

    def test_reports_correct_completion_percentage(self):
        dept = DepartmentFactory()
        user = UserFactory(department=dept)
        module = OnboardingModuleFactory()

        ModuleAssignmentFactory(user=user, module=module, status=ModuleAssignment.Status.COMPLETED)
        ModuleAssignmentFactory(
            user=user, module=module, status=ModuleAssignment.Status.NOT_STARTED
        )

        result = department_activity_report_list()

        row = next(r for r in result if r["department_id"] == dept.id)
        # 1 completed out of 2 total = 50%
        self.assertEqual(row["completion_percentage"], 50.0)

    def test_completion_percentage_zero_when_no_assignments(self):
        dept = DepartmentFactory()
        UserFactory(department=dept)

        result = department_activity_report_list()

        row = next(r for r in result if r["department_id"] == dept.id)
        self.assertEqual(row["completion_percentage"], 0.0)

    def test_reports_correct_activity_event_count(self):
        dept = DepartmentFactory()
        user1 = UserFactory(department=dept)
        user2 = UserFactory(department=dept)

        ActivityEventFactory(user=user1)
        ActivityEventFactory(user=user1)
        ActivityEventFactory(user=user2)

        result = department_activity_report_list()

        row = next(r for r in result if r["department_id"] == dept.id)
        self.assertEqual(row["activity_event_count"], 3)

    def test_includes_required_fields(self):
        dept = DepartmentFactory()

        result = department_activity_report_list()

        row = next(r for r in result if r["department_id"] == dept.id)
        self.assertIn("department_id", row)
        self.assertIn("department_name", row)
        self.assertIn("employee_count", row)
        self.assertIn("completion_percentage", row)
        self.assertIn("activity_event_count", row)
