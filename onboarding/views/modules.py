from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from api.pagination import LimitOffsetPagination, get_paginated_response
from onboarding.models import OnboardingModule
from onboarding.selectors import module_get, module_list


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
