from datetime import date, timedelta
from unittest.mock import patch

from django.core import mail
from django.test import TestCase
from django.utils import timezone

from onboarding.models import ActivityEvent, ModuleAssignment, OnboardingModule, User
from onboarding.services import overdue_reminders_send


class OverdueRemindersSendTests(TestCase):
    """The retry-safety exercise.

    `mail.outbox` works without any configuration here because Django's test runner
    swaps EMAIL_BACKEND for the in-memory backend during `manage.py test`, so the
    console backend configured in settings is never used under test.
    """

    def setUp(self):
        self.today = date(2026, 8, 7)
        self.module = OnboardingModule.objects.create(
            title="Benefits Enrolment",
            description="Choose a plan.",
            category=OnboardingModule.Category.BENEFITS,
        )

    def _user(self, username: str, email: str = "") -> User:
        return User.objects.create_user(
            username=username, password="x", email=email or f"{username}@example.com"
        )

    def _assignment(self, user: User, *, due: date, completed: bool = False) -> ModuleAssignment:
        return ModuleAssignment.objects.create(
            user=user,
            module=self.module,
            due_date=due,
            completed_at=timezone.now() if completed else None,
            status=(
                ModuleAssignment.Status.COMPLETED
                if completed
                else ModuleAssignment.Status.IN_PROGRESS
            ),
        )

    def test_emails_one_message_per_overdue_user(self):
        user = self._user("late")
        self._assignment(user, due=self.today - timedelta(days=3))

        result = overdue_reminders_send(as_of=self.today)

        self.assertEqual(result, {"as_of": "2026-08-07", "sent": 1})
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [user.email])
        self.assertIn("1 overdue", mail.outbox[0].subject)

    def test_one_email_covers_every_overdue_module(self):
        """A hire five modules behind gets one message, not five.

        This is why the selector returns users with a count rather than
        assignments.
        """
        user = self._user("verylate")
        for days in range(1, 6):
            self._assignment(user, due=self.today - timedelta(days=days))

        overdue_reminders_send(as_of=self.today)

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("5 overdue", mail.outbox[0].subject)

    def test_logs_one_activity_event_per_recipient(self):
        user = self._user("late")
        self._assignment(user, due=self.today - timedelta(days=1))

        overdue_reminders_send(as_of=self.today)

        event = ActivityEvent.objects.get(event_type="overdue_reminder_sent")
        self.assertEqual(event.user_id, user.id)
        self.assertEqual(event.metadata, {"overdue_count": 1, "as_of": "2026-08-07"})

    def test_skips_assignments_that_are_not_overdue(self):
        user = self._user("ontime")
        self._assignment(user, due=self.today + timedelta(days=2))

        overdue_reminders_send(as_of=self.today)

        self.assertEqual(len(mail.outbox), 0)

    def test_skips_completed_assignments(self):
        """Matches `ModuleAssignment.is_overdue`, which keys off completed_at."""
        user = self._user("done")
        self._assignment(user, due=self.today - timedelta(days=5), completed=True)

        overdue_reminders_send(as_of=self.today)

        self.assertEqual(len(mail.outbox), 0)

    def test_skips_users_without_an_email_address(self):
        user = User.objects.create_user(username="noemail", password="x", email="")
        self._assignment(user, due=self.today - timedelta(days=1))

        result = overdue_reminders_send(as_of=self.today)

        self.assertEqual(result["sent"], 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_skips_inactive_users(self):
        user = self._user("gone")
        user.is_active = False
        user.save(update_fields=["is_active"])
        self._assignment(user, due=self.today - timedelta(days=1))

        overdue_reminders_send(as_of=self.today)

        self.assertEqual(len(mail.outbox), 0)

    def test_running_twice_sends_once(self):
        """The reminder window, which is what makes a retry of the batch safe."""
        user = self._user("late")
        self._assignment(user, due=self.today - timedelta(days=1))

        overdue_reminders_send(as_of=self.today)
        second = overdue_reminders_send(as_of=self.today)

        self.assertEqual(second["sent"], 0)
        self.assertEqual(len(mail.outbox), 1)

    def test_sends_again_once_the_reminder_window_has_passed(self):
        user = self._user("late")
        self._assignment(user, due=self.today - timedelta(days=1))

        overdue_reminders_send(as_of=self.today)

        # Age the reminder past the 20 hour window rather than waiting for it.
        ActivityEvent.objects.filter(event_type="overdue_reminder_sent").update(
            occurred_at=timezone.now() - timedelta(hours=21)
        )

        overdue_reminders_send(as_of=self.today)

        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(user.activity_events.filter(event_type="overdue_reminder_sent").count(), 2)

    def test_a_failed_send_leaves_earlier_recipients_logged(self):
        """The reason the loop is not wrapped in one transaction.

        The exception propagates so the task's autoretry_for can see it, but
        whatever was already sent stays logged. One transaction around the batch
        would roll those log rows back, and the retry would email those people
        twice.
        """
        first = self._user("aaa")
        second = self._user("bbb")
        self._assignment(first, due=self.today - timedelta(days=1))
        self._assignment(second, due=self.today - timedelta(days=1))

        with patch("onboarding.services.modules.send_mail") as mock_send_mail:
            mock_send_mail.side_effect = [None, OSError("smtp unavailable")]

            with self.assertRaises(OSError):
                overdue_reminders_send(as_of=self.today)

        self.assertEqual(
            ActivityEvent.objects.filter(event_type="overdue_reminder_sent").count(), 1
        )
        self.assertEqual(
            ActivityEvent.objects.get(event_type="overdue_reminder_sent").user_id, first.id
        )

    def test_the_retry_resumes_rather_than_restarting(self):
        first = self._user("aaa")
        second = self._user("bbb")
        self._assignment(first, due=self.today - timedelta(days=1))
        self._assignment(second, due=self.today - timedelta(days=1))

        with patch("onboarding.services.modules.send_mail") as mock_send_mail:
            mock_send_mail.side_effect = [None, OSError("smtp unavailable")]
            with self.assertRaises(OSError):
                overdue_reminders_send(as_of=self.today)

            # Second attempt, as the task's retry would make it. Only the
            # recipient that never got a reminder is picked up.
            mock_send_mail.side_effect = None
            result = overdue_reminders_send(as_of=self.today)

            recipients = [call.kwargs["recipient_list"] for call in mock_send_mail.call_args_list]

        self.assertEqual(result["sent"], 1)
        self.assertEqual(recipients, [[first.email], [second.email], [second.email]])

    def test_defaults_as_of_to_today(self):
        user = self._user("late")
        self._assignment(user, due=timezone.localdate() - timedelta(days=1))

        result = overdue_reminders_send()

        self.assertEqual(result["as_of"], timezone.localdate().isoformat())
        self.assertEqual(result["sent"], 1)
        self.assertEqual(len(mail.outbox), 1)
