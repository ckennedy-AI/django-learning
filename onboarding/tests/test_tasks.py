from unittest.mock import patch

from django.conf import settings
from django.test import TestCase

from onboarding.models import Skill
from onboarding.tasks import (
    generate_skill_embedding,
    rollup_department_progress,
    score_assessment_attempt,
    send_overdue_reminders,
)


class GenerateSkillEmbeddingTests(TestCase):
    """Tests for `onboarding/tasks.py`.

    Flat `tests/test_tasks.py` rather than a `tests/tasks/` package, mirroring
    the layer it tests: Celery tasks are a single flat module, not one module per
    sub-domain, so a package here would be a directory holding one file forever.
    It gets promoted the same way `onboarding/tasks.py` would.

    The task is called as a plain function, with no worker, no broker, and no
    eager mode. That is the point of keeping tasks thin: `generate_skill_embedding`
    has nothing in it but an ID, a service call, and a return, so there is
    nothing here that needs Celery's machinery to exercise. Whether Celery
    actually delivers the message is a different question, answered by
    `manage.py inspect_task_result` against a running worker.
    """

    def setUp(self):
        self.skill = Skill.objects.create(name="Kombu", description="Messaging library.")

    @patch("onboarding.services.skills.embed_texts")
    def test_embeds_the_skill_and_returns_the_services_result(self, mock_embed_texts):
        mock_embed_texts.return_value = [[0.75] * 384]

        result = generate_skill_embedding(self.skill.id)

        self.skill.refresh_from_db()
        self.assertEqual(len(self.skill.embedding), 384)
        self.assertEqual(result, {"skill_id": self.skill.id, "dimensions": 384})

    @patch("onboarding.services.skills.embed_texts")
    def test_passes_the_description_to_the_embedding_provider(self, mock_embed_texts):
        mock_embed_texts.return_value = [[0.0] * 384]

        generate_skill_embedding(self.skill.id)

        # The worker reads current state by ID rather than trusting a snapshot
        # taken at enqueue time, so what gets embedded is whatever the row says
        # now.
        mock_embed_texts.assert_called_once_with(["Messaging library."])

    def test_propagates_a_missing_skill(self):
        missing_id = self.skill.id
        self.skill.delete()

        with self.assertRaises(Skill.DoesNotExist):
            generate_skill_embedding(missing_id)


class ThinTaskDelegationTests(TestCase):
    """Every task added in Phase 12 is a call-through, and that is all these check.

    Each task is exercised as a plain function with its service patched at
    `onboarding.tasks`. Patching there rather than in the service module is
    correct in this direction: the task imports its service inside the function
    body, so the lookup happens at call time against `onboarding.services`, and
    `patch` on the task module would not be consulted. What is patched here is
    therefore the name the task actually resolves.

    Behaviour lives in `tests/services/`, where it can be tested without any of
    this. What is worth asserting here is only that the task passes its argument
    through and returns the service's result unchanged, because a task that
    quietly reshapes a return value is a task that has business logic in it.
    """

    def test_score_assessment_attempt_delegates(self):
        with patch("onboarding.services.assessment_attempt_score") as mock_service:
            mock_service.return_value = {"attempt_id": 7, "passed": True, "scored": True}

            result = score_assessment_attempt(7)

        mock_service.assert_called_once_with(attempt_id=7)
        self.assertEqual(result, {"attempt_id": 7, "passed": True, "scored": True})

    def test_send_overdue_reminders_delegates(self):
        with patch("onboarding.services.overdue_reminders_send") as mock_service:
            mock_service.return_value = {"as_of": "2026-08-07", "sent": 3}

            result = send_overdue_reminders()

        # No arguments: beat has none to pass, and the service reads the clock.
        mock_service.assert_called_once_with()
        self.assertEqual(result, {"as_of": "2026-08-07", "sent": 3})

    def test_rollup_department_progress_delegates(self):
        with patch("onboarding.services.department_progress_rollup") as mock_service:
            mock_service.return_value = {"captured_on": "2026-08-07", "departments": 8}

            result = rollup_department_progress()

        mock_service.assert_called_once_with()
        self.assertEqual(result, {"captured_on": "2026-08-07", "departments": 8})


class TaskExecutionPolicyTests(TestCase):
    """Pins the execution policy Phase 12 configured, because nothing else can.

    Retries, time limits, queue routing, and the beat schedule are the kind of
    decision that is invisible until the day it is wrong: a route that no longer
    matches a task name, or a soft limit deleted during a refactor, changes
    nothing about how the code reads and everything about how it runs. These
    assertions are deliberately about the settings and decorators rather than
    about Celery's behaviour, which belongs to Celery's own test suite.
    """

    def test_the_embedding_task_is_routed_to_its_own_queue(self):
        self.assertEqual(
            settings.CELERY_TASK_ROUTES["onboarding.tasks.generate_skill_embedding"],
            {"queue": "embeddings"},
        )
        # The route is keyed by task name, so this is the assertion that catches a
        # rename or a move of tasks.py.
        self.assertEqual(generate_skill_embedding.name, "onboarding.tasks.generate_skill_embedding")

    def test_the_embedding_task_raises_the_default_time_limits(self):
        """A cold worker child loads the model before it encodes anything."""
        self.assertEqual(generate_skill_embedding.soft_time_limit, 120)
        self.assertEqual(generate_skill_embedding.time_limit, 150)
        self.assertGreater(
            generate_skill_embedding.soft_time_limit, settings.CELERY_TASK_SOFT_TIME_LIMIT
        )

    def test_the_soft_limit_leaves_a_grace_period_before_the_hard_kill(self):
        """The gap between the two is the only chance a task gets to clean up.

        Equal limits would make the soft limit useless, since SIGKILL would
        arrive in the same instant as the exception.
        """
        self.assertLess(settings.CELERY_TASK_SOFT_TIME_LIMIT, settings.CELERY_TASK_TIME_LIMIT)

    def test_the_reminder_task_retries_transient_send_failures_with_backoff(self):
        self.assertIn(OSError, send_overdue_reminders.autoretry_for)
        self.assertTrue(send_overdue_reminders.retry_backoff)
        self.assertTrue(send_overdue_reminders.retry_jitter)
        self.assertEqual(send_overdue_reminders.max_retries, 5)

    def test_the_other_tasks_do_not_retry(self):
        """Retrying a deterministic failure only produces it again, on a schedule."""
        for task in (score_assessment_attempt, rollup_department_progress):
            with self.subTest(task=task.name):
                self.assertEqual(getattr(task, "autoretry_for", ()), ())

    def test_both_scheduled_tasks_are_on_beat_and_expire(self):
        scheduled = {entry["task"] for entry in settings.CELERY_BEAT_SCHEDULE.values()}

        self.assertEqual(
            scheduled,
            {
                "onboarding.tasks.send_overdue_reminders",
                "onboarding.tasks.rollup_department_progress",
            },
        )
        for name, entry in settings.CELERY_BEAT_SCHEDULE.items():
            with self.subTest(entry=name):
                # Without an expiry, messages published while every worker was
                # down all run at once when one returns.
                self.assertIn("expires", entry["options"])
