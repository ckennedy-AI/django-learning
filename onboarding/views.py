from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from api.pagination import CursorPagination, LimitOffsetPagination, get_paginated_response
from api.utils import inline_serializer
from onboarding.embeddings import embed_texts
from onboarding.models import (
    ActivityEvent,
    OnboardingModule,
    Skill,
    TaskAssignment,
    User,
    UserSkill,
)
from onboarding.selectors import (
    activity_event_list,
    department_activity_report_list,
    module_get,
    module_list,
    skill_search,
    user_dashboard_get,
    user_get,
    user_reports_get,
    user_skills_list,
)
from onboarding.services import task_assignment_approve


class ModuleListApi(APIView):
    class Pagination(LimitOffsetPagination):
        pass

    class OutputSerializer(serializers.ModelSerializer):
        class Meta:
            model = OnboardingModule
            fields = ("id", "title", "category", "order")

    def get(self, request):
        modules = module_list()

        return get_paginated_response(
            pagination_class=self.Pagination,
            serializer_class=self.OutputSerializer,
            queryset=modules,
            request=request,
            view=self,
        )


class ModuleDetailApi(APIView):
    class OutputSerializer(serializers.ModelSerializer):
        class Meta:
            model = OnboardingModule
            fields = ("id", "title", "description", "category", "order")

    def get(self, request, module_id):
        module = module_get(module_id=module_id)
        serializer = self.OutputSerializer(module)
        return Response(serializer.data)


class ActivityEventListApi(APIView):
    class Pagination(CursorPagination):
        # occurred_at, not id. It satisfies the cursor requirements (set once on
        # creation, non-null, effectively unique, not a float), and it is the
        # field ActivityEvent's composite index leads with alongside user, so a
        # feed filtered by ?user_id= can seek through activity_user_occurred_idx.
        # Ordering by id instead would leave that index unusable for the filtered
        # feed, since no index covers (user, id).
        ordering = "-occurred_at"

    class FilterSerializer(serializers.Serializer):
        user_id = serializers.IntegerField(required=False)
        event_type = serializers.CharField(required=False)

    class OutputSerializer(serializers.ModelSerializer):
        class Meta:
            model = ActivityEvent
            fields = ("id", "user_id", "event_type", "metadata", "occurred_at")

    def get(self, request):
        filters_serializer = self.FilterSerializer(data=request.query_params)
        filters_serializer.is_valid(raise_exception=True)

        events = activity_event_list(filters=filters_serializer.validated_data)

        return get_paginated_response(
            pagination_class=self.Pagination,
            serializer_class=self.OutputSerializer,
            queryset=events,
            request=request,
            view=self,
        )


class UserDetailApi(APIView):
    class OutputSerializer(serializers.ModelSerializer):
        department = inline_serializer(
            fields={"id": serializers.IntegerField(), "name": serializers.CharField()}
        )
        manager = inline_serializer(
            fields={"id": serializers.IntegerField(), "username": serializers.CharField()}
        )

        class Meta:
            model = User
            fields = (
                "id",
                "username",
                "first_name",
                "last_name",
                "email",
                "department",
                "manager",
                "is_active",
                "date_joined",
            )

    def get(self, request, user_id):
        user = user_get(user_id=user_id)
        serializer = self.OutputSerializer(user)
        return Response(serializer.data)


class UserSkillsApi(APIView):
    class Pagination(LimitOffsetPagination):
        pass

    class OutputSerializer(serializers.ModelSerializer):
        name = serializers.CharField(source="skill.name")

        class Meta:
            model = UserSkill
            fields = ("skill_id", "name", "proficiency")

    def get(self, request, user_id):
        user_skills = user_skills_list(user_id=user_id)

        return get_paginated_response(
            pagination_class=self.Pagination,
            serializer_class=self.OutputSerializer,
            queryset=user_skills,
            request=request,
            view=self,
        )


class UserReportsApi(APIView):
    class OutputSerializer(serializers.ModelSerializer):
        manager = inline_serializer(
            fields={"id": serializers.IntegerField(), "username": serializers.CharField()}
        )
        direct_reports = inline_serializer(
            fields={"id": serializers.IntegerField(), "username": serializers.CharField()},
            many=True,
        )

        class Meta:
            model = User
            fields = ("id", "username", "manager", "direct_reports")

    def get(self, request, user_id):
        user = user_reports_get(user_id=user_id)
        serializer = self.OutputSerializer(user)
        return Response(serializer.data)


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


class SkillSearchApi(APIView):
    """Deliberately not paginated.

    The other conscious exception to the paginate-every-list rule. The result
    set is already bounded by the validated `limit` parameter, capped at 50, and
    a similarity search is asked for the closest few matches rather than paged
    through to the end. Adding a paginator on top would mean two mechanisms
    bounding the same response, with no obvious answer as to which wins.
    """

    class FilterSerializer(serializers.Serializer):
        q = serializers.CharField()
        limit = serializers.IntegerField(required=False, default=10, min_value=1, max_value=50)

    class OutputSerializer(serializers.ModelSerializer):
        distance = serializers.FloatField(read_only=True)

        class Meta:
            model = Skill
            fields = ("id", "name", "description", "distance")

    def get(self, request):
        filters_serializer = self.FilterSerializer(data=request.query_params)
        filters_serializer.is_valid(raise_exception=True)
        filters = filters_serializer.validated_data

        embedding = embed_texts([filters["q"]])[0]
        skills = skill_search(embedding=embedding, limit=filters["limit"])

        serializer = self.OutputSerializer(skills, many=True)
        return Response(serializer.data)


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
