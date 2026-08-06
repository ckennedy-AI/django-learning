from django.urls import reverse

from onboarding.models import Department
from onboarding.tests.views.base import EndpointFixtures


class DepartmentActivityReportApiTests(EndpointFixtures):
    def test_department_activity_report_scales_with_department_count(self):
        # Staff only. setUp authenticates as the plain employee fixture, so
        # this test switches to staff explicitly.
        self.authenticate_as(self.staff)

        # Deliberately unoptimized: one query per department for headcount, total
        # assignments, completed assignments, and activity event count.
        department_count = Department.objects.count()
        with self.assertNumQueries(1 + 4 * department_count):
            response = self.client.get(reverse("department-activity-report"))
        self.assertEqual(response.status_code, 200)

    def test_department_activity_report_rejects_non_staff(self):
        response = self.client.get(reverse("department-activity-report"))

        self.assertEqual(response.status_code, 403)
