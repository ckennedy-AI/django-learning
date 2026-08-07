from django.db import models
from django.utils import timezone

from onboarding.models.modules import OnboardingModule
from onboarding.models.users import User


class Assessment(models.Model):
    module = models.OneToOneField(
        OnboardingModule, on_delete=models.CASCADE, related_name="assessment"
    )
    passing_score = models.PositiveSmallIntegerField(default=80)

    class Meta:
        ordering = ["module__order"]

    def __str__(self) -> str:
        return f"Assessment for {self.module}"


class AssessmentQuestion(models.Model):
    assessment = models.ForeignKey(Assessment, on_delete=models.CASCADE, related_name="questions")
    text = models.TextField()
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order"]

    def __str__(self) -> str:
        return self.text[:50]


class AssessmentAttempt(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="assessment_attempts")
    assessment = models.ForeignKey(Assessment, on_delete=models.PROTECT, related_name="attempts")
    score = models.PositiveSmallIntegerField()
    attempted_at = models.DateTimeField(default=timezone.now)
    # Both null means "submitted but not scored yet", which is a real state
    # here: the attempt row is written by the request and scored by a worker, so
    # there is a window in between. `passed` is nullable rather than defaulting
    # to False because False would claim the attempt was scored and failed.
    #
    # scored_at is also the concurrency gate for score_assessment_attempt. That
    # service scores an attempt with UPDATE ... WHERE scored_at IS NULL and
    # trusts the affected row count, so this column is what makes running the
    # task twice safe. Do not let anything else write it.
    passed = models.BooleanField(null=True, blank=True)
    scored_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-attempted_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(score__gte=0) & models.Q(score__lte=100),
                name="score_between_0_and_100",
            ),
            # The two scoring columns are one fact, so the database enforces
            # that they move together. A constraint rather than a `clean()`
            # check on purpose: the writer here is a worker calling `.update()`,
            # which does not run `full_clean`, so a model-level check would not
            # be in the path that matters.
            models.CheckConstraint(
                condition=(
                    models.Q(scored_at__isnull=True, passed__isnull=True)
                    | models.Q(scored_at__isnull=False, passed__isnull=False)
                ),
                name="scored_at_and_passed_set_together",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user} - {self.assessment} - {self.score}"
