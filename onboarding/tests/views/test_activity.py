from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from onboarding.models import ActivityEvent
from onboarding.tests.views.base import EndpointFixtures


class ActivityEventListApiTests(EndpointFixtures):
    def test_activity_event_list_is_one_query(self):
        # Cursor pagination has no COUNT, which is half the reason it stays at one
        # query no matter how deep the page.
        with self.assertNumQueries(1):
            response = self.client.get(reverse("activity-event-list"))
        self.assertEqual(response.status_code, 200)

    def test_activity_event_list_filtered_by_user_is_one_query(self):
        with self.assertNumQueries(1):
            response = self.client.get(reverse("activity-event-list"), {"user_id": self.user.id})
        self.assertEqual(response.status_code, 200)

    def test_activity_event_list_pages_through_the_occurred_at_cursor(self):
        # The cursor field is occurred_at, a datetime, not an integer id. This
        # walks the whole feed through the next links to prove the datetime
        # round-trips through the opaque cursor without dropping or repeating a
        # row, which is the failure mode a non-unique or coarse cursor field
        # produces.
        now = timezone.now()
        for index in range(25):
            ActivityEvent.objects.create(
                user=self.user,
                event_type="page_view",
                occurred_at=now - timedelta(seconds=index),
            )

        seen_ids = []
        occurred_at_values = []
        url = reverse("activity-event-list")

        while url:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            for row in response.data["results"]:
                seen_ids.append(row["id"])
                occurred_at_values.append(row["occurred_at"])
            url = response.data["next"]

        total = ActivityEvent.objects.count()
        self.assertEqual(len(seen_ids), total)
        self.assertEqual(len(set(seen_ids)), total, "cursor paging repeated a row")
        self.assertEqual(
            occurred_at_values,
            sorted(occurred_at_values, reverse=True),
            "feed is not in descending occurred_at order",
        )
