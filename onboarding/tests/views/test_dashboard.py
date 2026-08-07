from django.urls import reverse

from onboarding.tests.views.base import EndpointFixtures


class MyDashboardApiTests(EndpointFixtures):
    def test_dashboard_is_two_queries_on_miss_zero_on_hit(self):
        # setUp authenticates as self.user, so this is always "my" dashboard now,
        # with no user_id parameter to smuggle someone else's in.
        with self.assertNumQueries(2):
            response = self.client.get(reverse("my-dashboard"))
        self.assertEqual(response.status_code, 200)

        with self.assertNumQueries(0):
            response = self.client.get(reverse("my-dashboard"))
        self.assertEqual(response.status_code, 200)
