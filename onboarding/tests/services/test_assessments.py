from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase

from onboarding.models import ActivityEvent, Assessment, AssessmentAttempt, OnboardingModule, User
from onboarding.services import assessment_attempt_create, assessment_attempt_score


class AssessmentAttemptCreateTests(TestCase):
    """The enqueue side, which is the same shape as SkillCreateTests.

    Patches the task at `onboarding.services.assessments`, the module that
    imported it, not at `onboarding.tasks` where it is defined: the service holds
    its own module-level reference, so patching the definition site would leave
    that reference pointing at the real task.
    """

    def setUp(self):
        self.user = User.objects.create_user(username="hire", password="x")
        module = OnboardingModule.objects.create(
            title="Security Awareness",
            description="Phishing and passwords.",
            category=OnboardingModule.Category.SECURITY,
        )
        self.assessment = Assessment.objects.create(module=module, passing_score=80)

    def test_writes_an_unscored_attempt(self):
        with patch("onboarding.services.assessments.score_assessment_attempt_task"):
            attempt, _ = assessment_attempt_create(
                user_id=self.user.id, assessment_id=self.assessment.id, score=90
            )

        attempt.refresh_from_db()
        self.assertEqual(attempt.score, 90)
        # The point of the async path: the attempt exists, the verdict does not
        # yet.
        self.assertIsNone(attempt.passed)
        self.assertIsNone(attempt.scored_at)

    def test_does_not_enqueue_before_commit(self):
        with patch("onboarding.services.assessments.score_assessment_attempt_task") as mock_task:
            assessment_attempt_create(
                user_id=self.user.id, assessment_id=self.assessment.id, score=90
            )

            mock_task.apply_async.assert_not_called()

    def test_enqueues_an_id_on_commit_with_the_returned_task_id(self):
        with patch("onboarding.services.assessments.score_assessment_attempt_task") as mock_task:
            with self.captureOnCommitCallbacks(execute=True):
                attempt, task_id = assessment_attempt_create(
                    user_id=self.user.id, assessment_id=self.assessment.id, score=90
                )

        mock_task.apply_async.assert_called_once_with(args=[attempt.id], task_id=task_id)
        self.assertIsInstance(mock_task.apply_async.call_args.kwargs["args"][0], int)

    def test_rejects_a_score_above_the_check_constraint(self):
        """full_clean validates the constraint, so this is a 400 rather than a 500.

        Django validates model constraints during full_clean, so the existing
        score_between_0_and_100 check is enforced in Python before the INSERT.
        Without that call the same input would reach Postgres and come back as an
        IntegrityError, which the exception handler has no field name for.
        """
        with patch("onboarding.services.assessments.score_assessment_attempt_task") as mock_task:
            with self.assertRaises(ValidationError):
                assessment_attempt_create(
                    user_id=self.user.id, assessment_id=self.assessment.id, score=101
                )

        self.assertEqual(AssessmentAttempt.objects.count(), 0)
        mock_task.apply_async.assert_not_called()


class AssessmentAttemptScoreTests(TestCase):
    """The idempotency exercise. These are the tests the phase is really about."""

    def setUp(self):
        self.user = User.objects.create_user(username="hire", password="x")
        module = OnboardingModule.objects.create(
            title="Company Policy",
            description="Handbook.",
            category=OnboardingModule.Category.POLICY,
        )
        self.assessment = Assessment.objects.create(module=module, passing_score=80)

    def _attempt(self, score: int) -> AssessmentAttempt:
        return AssessmentAttempt.objects.create(
            user=self.user, assessment=self.assessment, score=score
        )

    def test_marks_a_passing_attempt_and_logs_one_event(self):
        attempt = self._attempt(score=85)

        result = assessment_attempt_score(attempt_id=attempt.id)

        attempt.refresh_from_db()
        self.assertTrue(attempt.passed)
        self.assertIsNotNone(attempt.scored_at)
        self.assertEqual(result["passed"], True)
        self.assertTrue(result["scored"])

        event = ActivityEvent.objects.get(event_type="assessment_scored")
        self.assertEqual(event.user_id, self.user.id)
        self.assertEqual(event.metadata["attempt_id"], attempt.id)
        self.assertEqual(event.metadata["passed"], True)

    def test_marks_a_failing_attempt(self):
        attempt = self._attempt(score=79)

        assessment_attempt_score(attempt_id=attempt.id)

        attempt.refresh_from_db()
        self.assertFalse(attempt.passed)
        # Failing is still scored. `passed` being False and being None are two
        # different facts, which is why the column is nullable.
        self.assertIsNotNone(attempt.scored_at)

    def test_the_passing_score_is_inclusive(self):
        attempt = self._attempt(score=80)

        assessment_attempt_score(attempt_id=attempt.id)

        attempt.refresh_from_db()
        self.assertTrue(attempt.passed)

    def test_running_twice_scores_once_and_logs_once(self):
        """Idempotency, which is what makes a redelivered message harmless.

        The second call must not write a second ActivityEvent, and must report
        that it did not own the transition rather than pretending it did.
        """
        attempt = self._attempt(score=85)

        first = assessment_attempt_score(attempt_id=attempt.id)
        second = assessment_attempt_score(attempt_id=attempt.id)

        self.assertTrue(first["scored"])
        self.assertFalse(second["scored"])
        # The verdict is still reported on the duplicate path, re-read from the
        # row rather than from the stale instance.
        self.assertTrue(second["passed"])
        self.assertEqual(ActivityEvent.objects.filter(event_type="assessment_scored").count(), 1)

    def test_the_second_run_does_not_move_scored_at(self):
        attempt = self._attempt(score=85)

        assessment_attempt_score(attempt_id=attempt.id)
        attempt.refresh_from_db()
        first_scored_at = attempt.scored_at

        assessment_attempt_score(attempt_id=attempt.id)
        attempt.refresh_from_db()

        self.assertEqual(attempt.scored_at, first_scored_at)

    def test_a_changed_score_does_not_rescore(self):
        """The gate is `scored_at`, not the score, and that is deliberate.

        An attempt is a submitted answer, not a mutable draft. If the score is
        edited after scoring, re-running the task must not quietly issue a second
        verdict, because the ActivityEvent already told the rest of the system
        what happened.
        """
        attempt = self._attempt(score=85)
        assessment_attempt_score(attempt_id=attempt.id)

        AssessmentAttempt.objects.filter(id=attempt.id).update(score=10)
        result = assessment_attempt_score(attempt_id=attempt.id)

        attempt.refresh_from_db()
        self.assertFalse(result["scored"])
        self.assertTrue(attempt.passed)
        self.assertEqual(ActivityEvent.objects.filter(event_type="assessment_scored").count(), 1)

    def test_raises_for_a_missing_attempt(self):
        attempt = self._attempt(score=85)
        missing_id = attempt.id
        attempt.delete()

        with self.assertRaises(AssessmentAttempt.DoesNotExist):
            assessment_attempt_score(attempt_id=missing_id)
