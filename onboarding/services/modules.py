from datetime import date, timedelta

from django.core.mail import send_mail
from django.utils import timezone

from onboarding.models import ActivityEvent
from onboarding.selectors import module_assignment_overdue_user_list
from onboarding.selectors.modules import OVERDUE_REMINDER_EVENT_TYPE

# How far back to look for an existing reminder before sending another. Twenty
# hours rather than twenty-four: the scheduled run happens at the same time every
# day, and a full day's window would let a run that starts a minute early decide
# it had already sent today's reminder and skip everybody.
REMINDER_WINDOW = timedelta(hours=20)


def overdue_reminders_send(*, as_of: date | None = None) -> dict:
    """Emails every user with overdue modules, at most once per reminder window.

    Named `overdue_reminders_send` rather than `module_assignment_...` because
    the thing being created is a reminder; it lives in `services/modules.py`
    because the outcome it is about is an overdue `ModuleAssignment`, which is
    the first tie-breaker in CLAUDE.md for a function no endpoint reaches.

    Deliberately not wrapped in `transaction.atomic`, which is a documented
    exception to the project's "multi-step writes are atomic" rule and the whole
    reason this task is safe to retry. One transaction around the loop would
    mean a failure on the last recipient rolls back the reminder log for every
    earlier one, and the retry would then email all of them a second time.
    Instead each event row commits on its own, immediately after its send, so the
    log is a progress marker: a crash loses at most the one in flight, and the
    selector's `~Exists` check means the retry resumes where the run stopped.

    That makes the delivery guarantee at-least-once, not exactly-once, and the
    remaining window is real: if the mail is accepted and the process dies before
    the event row commits, that user gets a second email on the retry. Closing it
    would need the send and the log to be one transaction, which they cannot be,
    because an SMTP conversation cannot be rolled back. Duplicating a reminder is
    the cheaper failure than silently not sending one, so the order is send
    first, log second.

    Returns counts rather than the users, because the return value goes into the
    Celery result backend and has to be JSON.
    """
    as_of = as_of or timezone.localdate()
    reminded_since = timezone.now() - REMINDER_WINDOW

    recipients = module_assignment_overdue_user_list(as_of=as_of, reminded_since=reminded_since)

    sent = 0

    for user in recipients:
        send_mail(
            subject=f"You have {user.overdue_count} overdue onboarding module(s)",
            message=(
                f"Hi {user.get_short_name() or user.username},\n\n"
                f"{user.overdue_count} of your onboarding modules are past their "
                "due date. Sign in to the onboarding platform to finish them.\n"
            ),
            # None means DEFAULT_FROM_EMAIL, so the sender lives in settings
            # rather than in this string.
            from_email=None,
            recipient_list=[user.email],
            # fail_silently=False is the point of the retry configuration on the
            # task. A swallowed send error would leave a reminder logged that was
            # never delivered, which is worse than a task the worker retries.
            fail_silently=False,
        )

        ActivityEvent.objects.create(
            user=user,
            event_type=OVERDUE_REMINDER_EVENT_TYPE,
            metadata={"overdue_count": user.overdue_count, "as_of": as_of.isoformat()},
        )

        sent += 1

    return {"as_of": as_of.isoformat(), "sent": sent}
