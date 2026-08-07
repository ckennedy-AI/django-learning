from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from api.utils import inline_serializer
from onboarding.selectors import user_dashboard_get


class MyDashboardApi(APIView):
    class OutputSerializer(serializers.Serializer):
        module_assignments = inline_serializer(
            fields={
                "id": serializers.IntegerField(),
                "module_title": serializers.CharField(),
                "status": serializers.CharField(),
                "due_date": serializers.DateField(),
                "is_overdue": serializers.BooleanField(),
            },
            many=True,
        )
        pending_tasks = inline_serializer(
            fields={
                "id": serializers.IntegerField(),
                "task_title": serializers.CharField(),
                "status": serializers.CharField(),
            },
            many=True,
        )
        completion_percentage = serializers.FloatField()

    def get(self, request):
        dashboard = user_dashboard_get(user_id=request.user.id)

        serializer = self.OutputSerializer(dashboard)
        return Response(serializer.data)
