from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APITestCase

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


class EndpointFixtures(APITestCase):
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
        cls.staff = User.objects.create_user(username="staff", password="x", is_staff=True)

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

        # A non-zero vector, deliberately. A zero vector has no direction, so
        # cosine distance against it divides by a zero norm and yields NaN, and
        # an HNSW graph built over one cannot be navigated: the index scan
        # returns no rows at all for a small LIMIT, while a LIMIT above
        # hnsw.ef_search (40) falls back to a sequential scan and returns the row
        # with a NaN distance that DRF's JSON renderer then refuses to encode.
        # With [0.0] * 384 here, SkillSearchApiTests was asserting its query
        # count against an empty result set.
        cls.skill = Skill.objects.create(
            name="Django ORM", description="Query optimization.", embedding=[0.05] * 384
        )
        UserSkill.objects.create(user=cls.user, skill=cls.skill)

        ActivityEvent.objects.create(user=cls.user, event_type="login", occurred_at=timezone.now())

    def setUp(self):
        cache.clear()
        # Every endpoint requires a caller by default now, so every test needs
        # someone authenticated before it can reach the view at all. Defaulting
        # to the plain employee fixture keeps most existing tests unchanged;
        # a test exercising a manager-only or staff-only path calls
        # authenticate_as again with the fixture that path actually needs.
        self.authenticate_as(self.user)

    def authenticate_as(self, user):
        self.client.force_authenticate(user=user)
