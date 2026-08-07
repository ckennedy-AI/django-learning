from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from onboarding.tests.factories import AssessmentAttemptFactory


class AssessmentAttemptScoreBoundaryTests(TestCase):
    """The check constraint enforces score between 0 and 100 inclusive."""

    def test_a_score_of_negative_one_raises_integrity_error(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                AssessmentAttemptFactory(score=-1)

    def test_a_score_of_one_hundred_one_raises_integrity_error(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                AssessmentAttemptFactory(score=101)

    def test_a_score_of_exactly_zero_succeeds(self):
        attempt = AssessmentAttemptFactory(score=0)

        self.assertEqual(attempt.score, 0)

    def test_a_score_of_exactly_one_hundred_succeeds(self):
        attempt = AssessmentAttemptFactory(score=100)

        self.assertEqual(attempt.score, 100)

    def test_a_score_in_the_middle_succeeds(self):
        attempt = AssessmentAttemptFactory(score=75)

        self.assertEqual(attempt.score, 75)


class AssessmentAttemptScoredAtAndPassedSetTogetherTests(TestCase):
    """The constraint enforces that scored_at and passed move together.

    Both null is the initial state, submitted but not yet scored by a worker.
    Both set is the final state after the worker runs. One set and one null is
    an inconsistency the constraint prevents.
    """

    def test_both_null_succeeds(self):
        attempt = AssessmentAttemptFactory(scored_at=None, passed=None)

        self.assertIsNone(attempt.scored_at)
        self.assertIsNone(attempt.passed)

    def test_both_set_succeeds(self):
        now = timezone.now()
        attempt = AssessmentAttemptFactory(scored_at=now, passed=True)

        self.assertIsNotNone(attempt.scored_at)
        self.assertIsNotNone(attempt.passed)

    def test_only_scored_at_set_raises_integrity_error(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                AssessmentAttemptFactory(scored_at=timezone.now(), passed=None)

    def test_only_passed_set_raises_integrity_error(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                AssessmentAttemptFactory(scored_at=None, passed=True)
