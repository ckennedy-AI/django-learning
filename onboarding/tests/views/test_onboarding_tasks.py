from django.core.cache import cache
from django.urls import reverse

from onboarding.models import User
from onboarding.tests.views.base import EndpointFixtures


class TaskApprovalApiTests(EndpointFixtures):
    def test_task_approval_invalidates_dashboard_cache(self):
        # Warm the assignee's dashboard cache first, as the assignee.
        self.client.get(reverse("my-dashboard"))
        cache_key = f"onboarding:user_dashboard:{self.user.id}"
        self.assertIsNotNone(cache.get(cache_key))

        # Approval is the manager's action, not the assignee's, and there is
        # no manager_id body param anymore, it comes from request.user.
        self.authenticate_as(self.manager)

        # TestCase rolls back its transaction, so on_commit callbacks never fire
        # unless captured and executed explicitly.
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse("task-assignment-approve", args=[self.task_assignment.id])
            )

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(cache.get(cache_key))

    def test_task_approval_rejects_other_managers(self):
        other_manager = User.objects.create_user(username="other_manager", password="x")
        self.authenticate_as(other_manager)

        response = self.client.post(
            reverse("task-assignment-approve", args=[self.task_assignment.id])
        )

        self.assertEqual(response.status_code, 404)
