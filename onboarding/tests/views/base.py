from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from onboarding.models import (
    ActivityEvent,
    Department,
    ModuleAssignment,
    OnboardingModule,
    OnboardingTask,
    Skill,
    TaskAssignment,
    User,
    UserSkill,
)


class EndpointFixtures(TestCase):
    """One fixture set, shared by every view test, so query counts are comparable.

    The per-endpoint test cases in this package assert the exact query counts
    recorded in CLAUDE.md's endpoint table. A failure there means either a
    regression (someone added an N+1) or a deliberate optimization change, in
    which case update both the count and the CLAUDE.md row together.

    Those counts, and the two absolute assertions on `count` in the module and
    skills tests, are only meaningful against a known fixture set. That is why
    this lives in one place and is inherited rather than trimmed per file: a
    per-file fixture would make each number depend on a different database state,
    and a count changing for a fixture reason would look identical to a count
    changing for an N+1 reason.

    This file is deliberately not named `test_*.py`, so the test runner does not
    collect it as a module of its own.
    """

    @classmethod
    def setUpTestData(cls):
        cls.department = Department.objects.create(name="Engineering")

        cls.manager = User.objects.create_user(
            username="manager", password="x", department=cls.department
        )
        cls.user = User.objects.create_user(
            username="employee", password="x", department=cls.department, manager=cls.manager
        )

        cls.module = OnboardingModule.objects.create(
            title="Code of Conduct",
            description="Company policy overview.",
            category=OnboardingModule.Category.POLICY,
            order=1,
        )
        ModuleAssignment.objects.create(
            user=cls.user,
            module=cls.module,
            due_date=timezone.now().date(),
            status=ModuleAssignment.Status.COMPLETED,
            completed_at=timezone.now(),
        )

        cls.task = OnboardingTask.objects.create(
            title="Set up laptop", description="IT provisioning."
        )
        cls.task_assignment = TaskAssignment.objects.create(
            task=cls.task, assignee=cls.user, status=TaskAssignment.Status.COMPLETED
        )

        cls.skill = Skill.objects.create(
            name="Django ORM", description="Query optimization.", embedding=[0.0] * 384
        )
        UserSkill.objects.create(user=cls.user, skill=cls.skill)

        ActivityEvent.objects.create(user=cls.user, event_type="login", occurred_at=timezone.now())

    def setUp(self):
        cache.clear()
