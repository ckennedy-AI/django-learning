from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from onboarding.selectors import department_activity_report_list


class DepartmentActivityReportApi(APIView):
    """Deliberately not paginated.

    The rule is that every list endpoint is paginated, and this is a conscious
    exception rather than an oversight. The selector returns a list of dicts,
    one per department, and it has already run all of its queries by the time
    this view could slice it. Paginating would add an envelope without saving a
    single query, and the row count is bounded by the number of departments,
    which is small and grows only when the company reorganizes. If departments
    ever numbered in the hundreds, the fix is the annotated aggregate query, not
    pagination.
    """

    class OutputSerializer(serializers.Serializer):
        department_id = serializers.IntegerField()
        department_name = serializers.CharField()
        employee_count = serializers.IntegerField()
        completion_percentage = serializers.FloatField()
        activity_event_count = serializers.IntegerField()

    def get(self, request):
        report = department_activity_report_list()
        serializer = self.OutputSerializer(report, many=True)
        return Response(serializer.data)
