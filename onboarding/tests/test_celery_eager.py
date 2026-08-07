from django.test import TestCase

from onboarding.models import Assessment, OnboardingModule, User
from onboarding.services import assessment_attempt_create

"""Flat, mirroring flat onboarding/tasks.py, same reasoning as test_tasks.py:
one concern under test, so a package here would hold a single file forever.

Every enqueue test elsewhere in this suite (services/test_assessments.py,
services/test_skills.py, views/test_skills.py) patches the task it triggers,
because that is the only way to assert on the on_commit wiring in isolation
from what the task actually does. That leaves a real gap: nothing proves the
un-mocked chain, service enqueues, on_commit fires, the actual task body
runs, the row reflects it, ever works with no worker process involved.
CELERY_TASK_ALWAYS_EAGER under TESTING (config/settings.py) closes it by
running apply_async inline instead of publishing to Redis.

score_assessment_attempt is the task exercised here rather than
generate_skill_embedding, on purpose. The embedding task's body loads
all-MiniLM-L6-v2, and running that for real on every test invocation would
make this file slow and would coincidentally also test the embedding
provider rather than the eager-mode wiring. Scoring is pure database logic
with no external model to load, so it proves the same wiring at a fraction
of the cost.
"""


class AssessmentAttemptCreateEagerTests(TestCase):
    def setUp(self):
        module = OnboardingModule.objects.create(
            title="Security Basics",
            description="Phishing, passwords, physical access.",
            category=OnboardingModule.Category.SECURITY,
            order=1,
        )
        self.assessment = Assessment.objects.create(module=module, passing_score=80)
        self.user = User.objects.create_user(username="hire", password="x")

    def test_the_real_task_runs_inline_and_scores_the_attempt(self):
        """No patch on score_assessment_attempt_task anywhere in this test.

        Without CELERY_TASK_ALWAYS_EAGER, apply_async would publish a message
        to Redis and this assertion would fail every time, since nothing in
        the test process would ever consume it. With it on, apply_async runs
        assessment_attempt_score synchronously the moment the on_commit
        callback fires, so the row is already scored by the time this
        function returns.
        """
        with self.captureOnCommitCallbacks(execute=True):
            attempt, task_id = assessment_attempt_create(
                user_id=self.user.id, assessment_id=self.assessment.id, score=90
            )

        attempt.refresh_from_db()
        self.assertTrue(attempt.passed)
        self.assertIsNotNone(attempt.scored_at)
        self.assertIsInstance(task_id, str)

    def test_a_failing_score_is_scored_the_same_way(self):
        """Both outcomes of the real scoring logic, not just the happy path."""
        with self.captureOnCommitCallbacks(execute=True):
            attempt, _ = assessment_attempt_create(
                user_id=self.user.id, assessment_id=self.assessment.id, score=50
            )

        attempt.refresh_from_db()
        self.assertFalse(attempt.passed)
        self.assertIsNotNone(attempt.scored_at)
