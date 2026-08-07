from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from onboarding.embeddings import embed_texts
from onboarding.models import Skill
from onboarding.permissions import IsStaff
from onboarding.selectors import skill_search
from onboarding.services import skill_create


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


class SkillCreateApi(APIView):
    """Creates a skill and returns immediately, before it has been embedded.

    Contrast with SkillSearchApi above, which embeds synchronously in the
    request: a search cannot return a response before its own query vector
    exists, so there is nothing to move off the request cycle there. A create
    can, so it does.
    """

    # IsAuthenticated is already the project default, and it is repeated
    # explicitly here because declaring permission_classes replaces the default
    # list rather than adding to it. Naming only IsStaff would silently drop the
    # authentication requirement, and IsStaff's own check would still pass for
    # nobody, since AnonymousUser.is_staff is False. Writing both keeps the
    # endpoint's rule readable next to the permissions table.
    permission_classes = [IsAuthenticated, IsStaff]

    class InputSerializer(serializers.Serializer):
        name = serializers.CharField(max_length=150)
        description = serializers.CharField()

    class OutputSerializer(serializers.ModelSerializer):
        # Not a model field. The task id is the caller's handle for looking up
        # whether the embedding has landed, which is the only part of this
        # resource that is not final at 201.
        embedding_task_id = serializers.CharField(read_only=True)

        class Meta:
            model = Skill
            fields = ("id", "name", "description", "embedding_task_id")

    def post(self, request):
        serializer = self.InputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        skill, embedding_task_id = skill_create(**serializer.validated_data)

        # 201 rather than 202. The resource exists and is addressable the moment
        # this returns; one of its fields is pending. 202 would tell the client
        # the skill itself might not be there yet, which is a different and
        # inaccurate contract.
        output = self.OutputSerializer(skill).data
        output["embedding_task_id"] = embedding_task_id
        return Response(output, status=201)
