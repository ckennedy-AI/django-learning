from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from onboarding.models import TaskAssignment
from onboarding.services import task_assignment_approve


class TaskApprovalApi(APIView):
    class InputSerializer(serializers.Serializer):
        manager_id = serializers.IntegerField()

    class OutputSerializer(serializers.ModelSerializer):
        class Meta:
            model = TaskAssignment
            fields = ("id", "status", "approved_at")

    def post(self, request, task_assignment_id):
        input_serializer = self.InputSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)

        task_assignment = task_assignment_approve(
            task_assignment_id=task_assignment_id,
            manager_id=input_serializer.validated_data["manager_id"],
        )

        serializer = self.OutputSerializer(task_assignment)
        return Response(serializer.data)
