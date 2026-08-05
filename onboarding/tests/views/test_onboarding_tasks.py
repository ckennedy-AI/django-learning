from django.core.cache import cache
from django.urls import reverse

from onboarding.models import User
from onboarding.tests.views.base import EndpointFixtures


class TaskApprovalApiTests(EndpointFixtures):
    def test_task_approval_invalidates_dashboard_cache(self):
        # Warm the assignee's dashboard cache first.
        self.client.get(reverse("my-dashboard"), {"user_id": self.user.id})
        cache_key = f"onboarding:user_dashboard:{self.user.id}"
        self.assertIsNotNone(cache.get(cache_key))

        # TestCase rolls back its transaction, so on_commit callbacks never fire
        # unless captured and executed explicitly.
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse("task-assignment-approve", args=[self.task_assignment.id]),
                data={"manager_id": self.manager.id},
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(cache.get(cache_key))

    def test_task_approval_rejects_other_managers(self):
        other_manager = User.objects.create_user(username="other_manager", password="x")

        response = self.client.post(
            reverse("task-assignment-approve", args=[self.task_assignment.id]),
            data={"manager_id": other_manager.id},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 404)
