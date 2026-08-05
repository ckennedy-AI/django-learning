from django.db.models import QuerySet

from onboarding.models import ActivityEvent


def activity_event_list(*, filters: dict | None = None) -> QuerySet[ActivityEvent]:
    filters = filters or {}

    queryset = ActivityEvent.objects.all()

    if user_id := filters.get("user_id"):
        queryset = queryset.filter(user_id=user_id)

    if event_type := filters.get("event_type"):
        queryset = queryset.filter(event_type=event_type)

    return queryset
