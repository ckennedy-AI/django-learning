from django.core.exceptions import PermissionDenied
from django.db.models import QuerySet

from onboarding.models import ActivityEvent, User


def activity_event_list(
    *, requesting_user: User, filters: dict | None = None
) -> QuerySet[ActivityEvent]:
    """Self by default. A manager may pass user_id for one direct report.

    Staff may pass any user_id unrestricted. The row scope depends on who is
    asking, not just on the filter value, so the decision lives here rather
    than in a permission class: a permission class answers yes or no about
    the caller, it does not run the query needed to know whether the target
    user reports to them.

    A manager requesting an unrelated user's feed gets 403, not 404. Unlike
    TaskApprovalApi, whether a given user is or isn't this manager's report
    is not sensitive: org-chart membership is visible on UserReportsApi
    already, so there is nothing to hide by returning 404 instead.
    """
    filters = filters or {}
    target_user_id = filters.get("user_id")

    if target_user_id is None or target_user_id == requesting_user.id:
        scoped_user_id = requesting_user.id
    elif requesting_user.is_staff:
        scoped_user_id = target_user_id
    elif User.objects.filter(id=target_user_id, manager_id=requesting_user.id).exists():
        scoped_user_id = target_user_id
    else:
        raise PermissionDenied("You may only view your own activity feed or a direct report's.")

    queryset = ActivityEvent.objects.filter(user_id=scoped_user_id)

    if event_type := filters.get("event_type"):
        queryset = queryset.filter(event_type=event_type)

    return queryset
