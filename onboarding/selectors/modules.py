from datetime import date, datetime

from django.db.models import Count, Exists, OuterRef, Q, QuerySet
from django.shortcuts import get_object_or_404

from onboarding.models import ActivityEvent, OnboardingModule, User

# The event_type written by overdue_reminders_send and read back by the selector
# below to decide who has already been reminded. One constant rather than the
# string in two files, because a typo in either place turns the de-duplication
# off without failing anything.
OVERDUE_REMINDER_EVENT_TYPE = "overdue_reminder_sent"


def module_list() -> QuerySet[OnboardingModule]:
    return OnboardingModule.objects.all()


def module_get(*, module_id: int) -> OnboardingModule:
    return get_object_or_404(OnboardingModule, id=module_id)


def module_assignment_overdue_user_list(*, as_of: date, reminded_since: datetime) -> QuerySet[User]:
    """Users who have at least one overdue module assignment and no recent reminder.

    Returns users rather than assignments deliberately: the reminder is one
    email per person listing how far behind they are, not one email per
    assignment. A hire with five overdue modules gets one message, and the
    `overdue_count` annotation is what the body needs.

    Serves `overdue_reminders_send`, so it lives in `selectors/modules.py`
    beside its caller's sub-domain even though it returns `User` rows. The
    outcome the reminder is about is an overdue `ModuleAssignment`.

    Two filters, doing two different jobs:

    - `overdue_count` counts only assignments that are past due and not
      completed, using `completed_at__isnull=True` to match
      `ModuleAssignment.is_overdue` exactly rather than checking `status`. The
      count is done with a filtered aggregate and then filtered on, instead of
      filtering the join first, because filtering a reverse relation and
      counting it in the same queryset multiplies rows and inflates the count.
    - `~Exists(...)` drops anyone already reminded since `reminded_since`. This
      is what makes the task safe to retry: a batch that dies halfway through
      re-runs and only picks up whoever is left, because the reminder log is the
      progress marker. It also means a run that is triggered twice in an hour
      sends nothing the second time.

    Users with no email address are excluded here rather than skipped in the
    service, so the count the service reports is the count it actually sent.

    Ordered by `id` explicitly, overriding `User.Meta.ordering`. Two reasons, and
    neither is cosmetic. A batch that can die partway through should resume in the
    same order it started, and `username` is a text column with no index behind
    it, so sorting a grouped query by it costs more than sorting by the primary
    key. Leaving the default in place would also feed `username` into the GROUP BY
    that the aggregate below creates, which is a subtlety worth not relying on.

    One query. The `Exists` subquery is correlated, so it is part of the same
    statement rather than a second round trip.
    """
    already_reminded = ActivityEvent.objects.filter(
        user_id=OuterRef("id"),
        event_type=OVERDUE_REMINDER_EVENT_TYPE,
        occurred_at__gte=reminded_since,
    )

    return (
        User.objects.annotate(
            overdue_count=Count(
                "module_assignments",
                filter=Q(
                    module_assignments__due_date__lt=as_of,
                    module_assignments__completed_at__isnull=True,
                ),
            )
        )
        .filter(overdue_count__gt=0, is_active=True)
        .exclude(email="")
        .filter(~Exists(already_reminded))
        .order_by("id")
    )
