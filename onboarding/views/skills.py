from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from onboarding.embeddings import embed_texts
from onboarding.models import Skill
from onboarding.selectors import skill_search


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
