from django.urls import reverse

from onboarding.tests.views.base import EndpointFixtures


class MyDashboardApiTests(EndpointFixtures):
    def test_dashboard_is_two_queries_on_miss_zero_on_hit(self):
        with self.assertNumQueries(2):
            response = self.client.get(reverse("my-dashboard"), {"user_id": self.user.id})
        self.assertEqual(response.status_code, 200)

        with self.assertNumQueries(0):
            response = self.client.get(reverse("my-dashboard"), {"user_id": self.user.id})
        self.assertEqual(response.status_code, 200)
