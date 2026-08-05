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

    class Meta:
        ordering = ["-attempted_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(score__gte=0) & models.Q(score__lte=100),
                name="score_between_0_and_100",
            )
        ]

    def __str__(self) -> str:
        return f"{self.user} - {self.assessment} - {self.score}"
