from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from api.pagination import LimitOffsetPagination, get_paginated_response
from api.utils import inline_serializer
from onboarding.models import User, UserSkill
from onboarding.selectors import user_get, user_list, user_reports_get, user_skills_list


class UserListApi(APIView):
    """The company directory, paginated.

    OutputSerializer is a plain Serializer, not a ModelSerializer, because
    `user_list` hands back dicts shaped by its own annotations rather than
    `User` instances, and `name`/`manager_name`/`department_name` are not
    fields on the model at all.
    """

    class Pagination(LimitOffsetPagination):
        pass

    class FilterSerializer(serializers.Serializer):
        username = serializers.CharField(required=False)

    class OutputSerializer(serializers.Serializer):
        id = serializers.IntegerField()
        username = serializers.CharField()
        name = serializers.CharField()
        email = serializers.EmailField()
        is_staff = serializers.BooleanField()
        is_active = serializers.BooleanField()
        manager_name = serializers.CharField()
        department_name = serializers.CharField(allow_null=True)

    def get(self, request):
        filters_serializer = self.FilterSerializer(data=request.query_params)
        filters_serializer.is_valid(raise_exception=True)

        users = user_list(filters=filters_serializer.validated_data)

        return get_paginated_response(
            pagination_class=self.Pagination,
            serializer_class=self.OutputSerializer,
            queryset=users,
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
