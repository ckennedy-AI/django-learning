from django.urls import reverse

from onboarding.tests.views.base import EndpointFixtures


class ModuleListApiTests(EndpointFixtures):
    def test_module_list_is_two_queries(self):
        # LimitOffsetPagination costs a COUNT on top of the page query. That is
        # the price of an unbounded list becoming bounded, and it is worth it
        # here: without it the endpoint would serialize every module in the
        # catalogue on every call.
        with self.assertNumQueries(2):
            response = self.client.get(reverse("module-list"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("results", response.data)
        self.assertEqual(response.data["count"], 1)


class ModuleDetailApiTests(EndpointFixtures):
    def test_module_detail_is_one_query(self):
        with self.assertNumQueries(1):
            response = self.client.get(reverse("module-detail", args=[self.module.id]))
        self.assertEqual(response.status_code, 200)
