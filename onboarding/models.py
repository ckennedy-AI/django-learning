from datetime import date

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
from pgvector.django import HnswIndex, VectorField


class Department(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class User(AbstractUser):
    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="employees",
    )
    manager = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="direct_reports",
    )

    class Meta:
        ordering = ["username"]

    def __str__(self) -> str:
        return self.get_full_name() or self.username

    def get_direct_reports(self):
        return self.direct_reports.all()


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
    module = models.ForeignKey(OnboardingModule, on_delete=models.PROTECT, related_name="assignments")
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


class Assessment(models.Model):
    module = models.OneToOneField(OnboardingModule, on_delete=models.CASCADE, related_name="assessment")
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
    approver = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_task_assignments",
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-id"]

    def __str__(self) -> str:
        return f"{self.task} -> {self.assignee}"


class Skill(models.Model):
    name = models.CharField(max_length=150, unique=True)
    description = models.TextField()
    embedding = VectorField(dimensions=384)

    class Meta:
        ordering = ["name"]
        indexes = [
            HnswIndex(
                name="skill_embedding_hnsw",
                fields=["embedding"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            )
        ]

    def __str__(self) -> str:
        return self.name


class UserSkill(models.Model):
    class Proficiency(models.TextChoices):
        BEGINNER = "beginner", "Beginner"
        INTERMEDIATE = "intermediate", "Intermediate"
        EXPERT = "expert", "Expert"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="skills")
    skill = models.ForeignKey(Skill, on_delete=models.CASCADE, related_name="user_skills")
    proficiency = models.CharField(
        max_length=20, choices=Proficiency.choices, default=Proficiency.BEGINNER
    )

    class Meta:
        ordering = ["user", "skill"]
        constraints = [models.UniqueConstraint(fields=["user", "skill"], name="unique_user_skill")]

    def __str__(self) -> str:
        return f"{self.user} - {self.skill}"


class ActivityEvent(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="activity_events")
    event_type = models.CharField(max_length=100, db_index=True)
    metadata = models.JSONField(default=dict, blank=True)
    occurred_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-occurred_at"]
        indexes = [
            # Each of these three exists because an EXPLAIN ANALYZE plan asked for
            # it. All three lead with a filter ActivityEventListApi actually
            # accepts and end with occurred_at, the cursor field, so the planner
            # can seek to the cursor position instead of sorting to find it. See
            # `manage.py explain_queries`.
            #
            # The user-scoped feed. Measured 0.26 ms for a 20 row page.
            models.Index(fields=["user", "-occurred_at"], name="activity_user_occurred_idx"),
            # The unfiltered feed, which is the default request. Without this the
            # composite index above cannot help, since it leads with user and
            # there is no user predicate to seek on, so a 100,000 row table was
            # costing a parallel sequential scan plus a top-N sort, measured at
            # 22 ms.
            models.Index(fields=["-occurred_at"], name="activity_occurred_idx"),
            # The event_type-scoped feed. The plain db_index on event_type finds
            # the matching rows but cannot return them in cursor order, so a
            # single event type was reading 11,099 rows and sorting them to
            # return 20, measured at 15.6 ms.
            models.Index(fields=["event_type", "-occurred_at"], name="activity_type_occurred_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.event_type} ({self.user})"
