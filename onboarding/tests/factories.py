"""Factories for test data, flat file rather than a package.

One factory class per model in onboarding.models. Tests instantiate these instead
of hand-rolling Model.objects.create(...) calls, so test data is consistent and
any fixture-wide requirement (unique fields, reasonable defaults) lives in one
place.
"""

from datetime import date

import factory
from django.utils import timezone
from factory.django import DjangoModelFactory

from onboarding.models import (
    ActivityEvent,
    Assessment,
    AssessmentAttempt,
    AssessmentQuestion,
    Department,
    DepartmentProgressSnapshot,
    ModuleAssignment,
    OnboardingModule,
    OnboardingTask,
    Skill,
    TaskAssignment,
    User,
    UserSkill,
)


class DepartmentFactory(DjangoModelFactory):
    class Meta:
        model = Department

    name = factory.Sequence(lambda n: f"Department {n}")
    description = "A company department."


class UserFactory(DjangoModelFactory):
    """User.manager defaults to None, not a SubFactory.

    User.manager is self-referential, and a SubFactory would recurse infinitely
    trying to build a manager for the manager for the manager. A test that needs
    a manager passes one explicitly: UserFactory(manager=some_other_user).
    """

    class Meta:
        model = User

    username = factory.Sequence(lambda n: f"user{n}")
    email = factory.Sequence(lambda n: f"user{n}@example.com")
    first_name = "First"
    last_name = "Last"
    password = factory.PostGenerationMethodCall("set_password", "password123")
    department = factory.SubFactory(DepartmentFactory)
    manager = None


class OnboardingModuleFactory(DjangoModelFactory):
    class Meta:
        model = OnboardingModule

    title = factory.Sequence(lambda n: f"Module {n}")
    description = "An onboarding module."
    category = OnboardingModule.Category.POLICY
    order = 0


class ModuleAssignmentFactory(DjangoModelFactory):
    class Meta:
        model = ModuleAssignment

    user = factory.SubFactory(UserFactory)
    module = factory.SubFactory(OnboardingModuleFactory)
    status = ModuleAssignment.Status.NOT_STARTED
    due_date = factory.LazyFunction(date.today)
    completed_at = None


class OnboardingTaskFactory(DjangoModelFactory):
    class Meta:
        model = OnboardingTask

    title = factory.Sequence(lambda n: f"Task {n}")
    description = "An onboarding task."
    requires_approval = True


class TaskAssignmentFactory(DjangoModelFactory):
    class Meta:
        model = TaskAssignment

    task = factory.SubFactory(OnboardingTaskFactory)
    assignee = factory.SubFactory(UserFactory)
    approver = None
    status = TaskAssignment.Status.PENDING
    completed_at = None
    approved_at = None


class SkillFactory(DjangoModelFactory):
    """Skill.embedding defaults to a non-zero 384-dimension vector.

    A zero vector breaks pgvector search: cosine distance divides by the
    vector's norm, yielding NaN, and an HNSW graph cannot be navigated through
    a zero-vector row. A test that explicitly wants the pending state (skill
    exists without embedding) overrides it: SkillFactory(embedding=None).
    """

    class Meta:
        model = Skill

    name = factory.Sequence(lambda n: f"Skill {n}")
    description = "A skill."
    embedding = [0.1] * 384


class UserSkillFactory(DjangoModelFactory):
    class Meta:
        model = UserSkill

    user = factory.SubFactory(UserFactory)
    skill = factory.SubFactory(SkillFactory)
    proficiency = UserSkill.Proficiency.BEGINNER


class AssessmentFactory(DjangoModelFactory):
    class Meta:
        model = Assessment

    module = factory.SubFactory(OnboardingModuleFactory)
    passing_score = 80


class AssessmentQuestionFactory(DjangoModelFactory):
    class Meta:
        model = AssessmentQuestion

    assessment = factory.SubFactory(AssessmentFactory)
    text = "A sample question."
    order = 0


class AssessmentAttemptFactory(DjangoModelFactory):
    class Meta:
        model = AssessmentAttempt

    user = factory.SubFactory(UserFactory)
    assessment = factory.SubFactory(AssessmentFactory)
    score = 75
    attempted_at = factory.LazyFunction(timezone.now)
    passed = None
    scored_at = None


class DepartmentProgressSnapshotFactory(DjangoModelFactory):
    class Meta:
        model = DepartmentProgressSnapshot

    department = factory.SubFactory(DepartmentFactory)
    captured_on = factory.LazyFunction(date.today)
    employee_count = 10
    completion_percentage = 50.0
    activity_event_count = 5


class ActivityEventFactory(DjangoModelFactory):
    class Meta:
        model = ActivityEvent

    user = factory.SubFactory(UserFactory)
    event_type = "event"
    metadata = {}
    occurred_at = factory.LazyFunction(timezone.now)
