from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from api.utils import inline_serializer
from onboarding.selectors import user_dashboard_get


class MyDashboardApi(APIView):
    class FilterSerializer(serializers.Serializer):
        # Stand-in for request.user.id until JWT auth (Phase 10) is wired up.
        user_id = serializers.IntegerField()

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
        filters_serializer = self.FilterSerializer(data=request.query_params)
        filters_serializer.is_valid(raise_exception=True)

        dashboard = user_dashboard_get(user_id=filters_serializer.validated_data["user_id"])

        serializer = self.OutputSerializer(dashboard)
        return Response(serializer.data)
