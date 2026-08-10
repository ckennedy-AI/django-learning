from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from onboarding.models import TaskAssignment
from onboarding.permissions import IsAssigneeManager
from onboarding.selectors import task_assignment_get_for_manager
from onboarding.services import task_assignment_approve


class TaskApprovalApi(APIView):
    """POST, empty body. manager_id used to come from the request body; it
    is now request.user.id, since there is a real caller to read it from.

    The selector fetch here is a second read on top of the one
    task_assignment_approve already does inside its own transaction.atomic.
    That duplication is deliberate rather than an oversight: this fetch
    exists only to give check_object_permissions an object to check before
    any write happens, and the service re-fetches fresh state right before
    mutating rather than trusting a read taken outside its transaction.
    Query count for this endpoint moves from 1 read + 2 writes (Phase 9) to
    2 reads + 2 writes, traded for an explicit, declared permission check
    per caveat 15 instead of relying solely on the selector's WHERE clause.
    """

    # permission_classes on a view replaces DEFAULT_PERMISSION_CLASSES rather
    # than extending it, so IsAuthenticated has to be listed again alongside
    # the object-level check.
    permission_classes = [IsAuthenticated, IsAssigneeManager]

    class OutputSerializer(serializers.ModelSerializer):
        class Meta:
            model = TaskAssignment
            fields = ("id", "status", "approved_at")

    def post(self, request, task_assignment_id):
        task_assignment = task_assignment_get_for_manager(
            task_assignment_id=task_assignment_id, manager_id=request.user.id
        )
        self.check_object_permissions(request, task_assignment)

        task_assignment = task_assignment_approve(
            task_assignment_id=task_assignment_id,
            manager_id=request.user.id,
        )

        serializer = self.OutputSerializer(task_assignment)
        return Response(serializer.data)
