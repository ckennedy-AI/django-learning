from rest_framework import serializers
from rest_framework.views import APIView

from api.pagination import CursorPagination, get_paginated_response
from onboarding.models import ActivityEvent
from onboarding.selectors import activity_event_list


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
