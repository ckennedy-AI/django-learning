from datetime import date

from django.db import models

from onboarding.models.users import User


class OnboardingModule(models.Model):
    class Category(models.TextChoices):
        POLICY = "policy", "Policy"
        SECURITY = "security", "Security"
        BENEFITS = "benefits", "Benefits"
        CULTURE = "culture", "Culture"

    title = models.CharField(max_length=200)
    description = models.TextField()
    category = models.CharField(max_length=20, choices=Category.choices, db_index=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "title"]

    def __str__(self) -> str:
        return self.title


class ModuleAssignmentQuerySet(models.QuerySet):
    def incomplete(self):
        return self.exclude(status=ModuleAssignment.Status.COMPLETED)


class ModuleAssignment(models.Model):
    class Status(models.TextChoices):
        NOT_STARTED = "not_started", "Not started"
        IN_PROGRESS = "in_progress", "In progress"
        COMPLETED = "completed", "Completed"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="module_assignments")
    module = models.ForeignKey(
        OnboardingModule, on_delete=models.PROTECT, related_name="assignments"
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.NOT_STARTED, db_index=True
    )
    due_date = models.DateField()
    completed_at = models.DateTimeField(null=True, blank=True)

    objects = ModuleAssignmentQuerySet.as_manager()

    class Meta:
        ordering = ["due_date"]

    def __str__(self) -> str:
        return f"{self.user} - {self.module}"

    @property
    def is_overdue(self) -> bool:
        if self.completed_at is not None:
            return False
        return date.today() > self.due_date
