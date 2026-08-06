from django.db import models

from onboarding.models.departments import Department
from onboarding.models.users import User


class OnboardingTask(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField()
    requires_approval = models.BooleanField(default=True)
    departments = models.ManyToManyField(Department, related_name="onboarding_tasks", blank=True)

    class Meta:
        ordering = ["title"]

    def __str__(self) -> str:
        return self.title


class TaskAssignment(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        COMPLETED = "completed", "Completed"
        APPROVED = "approved", "Approved"

    task = models.ForeignKey(OnboardingTask, on_delete=models.PROTECT, related_name="assignments")
    assignee = models.ForeignKey(User, on_delete=models.CASCADE, related_name="task_assignments")
    approver = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="approved_task_assignments")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-id"]

    def __str__(self) -> str:
        return f"{self.task} -> {self.assignee}"
