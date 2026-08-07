import random
from collections.abc import Iterator
from datetime import date, datetime, time, timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from faker import Faker

from onboarding.embeddings import embed_texts
from onboarding.models import (
    ActivityEvent,
    Assessment,
    AssessmentAttempt,
    AssessmentQuestion,
    Department,
    ModuleAssignment,
    OnboardingModule,
    OnboardingTask,
    Skill,
    TaskAssignment,
    User,
    UserSkill,
)

DEPARTMENT_NAMES = [
    "Engineering",
    "Product",
    "Sales",
    "Marketing",
    "Customer Success",
    "People Operations",
    "Finance",
    "Legal",
]

# Fixed layers, not a random count. Layer 0 has no manager. Every later layer
# draws its managers only from users created in strictly earlier layers, which
# makes a reporting cycle structurally impossible rather than something to
# validate after the fact.
#
# Sized at 280 total users, not the smaller headcount from the first pass of
# this command, because AssessmentAttempt is documented in CLAUDE.md as a
# volume table of several thousand rows. A few dozen users cannot reach that
# without an unbelievable number of retakes per person. At this size, users
# times assessments times a realistic 1 to 3 attempts lands in the
# several-thousand range without inflating any single user's retake count.
LEADERSHIP_COUNT = 2
LAYER_SIZES = [8, 30, 80, 160]

HIRE_WINDOW_MIN_DAYS = 14
HIRE_WINDOW_MAX_DAYS = 450

BULK_BATCH_SIZE = 5000

EVENT_TYPES = [
    "login",
    "module_started",
    "module_completed",
    "assessment_attempted",
    "task_completed",
    "task_approved",
    "profile_updated",
    "skill_added",
    "overdue_reminder_sent",
]

MODULE_CATALOG = {
    OnboardingModule.Category.POLICY: [
        ("Code of Conduct", "Expected behavior, conflicts of interest, and reporting channels."),
        ("Remote Work Policy", "Working hours, expense reimbursement, and equipment policy."),
    ],
    OnboardingModule.Category.SECURITY: [
        ("Phishing Awareness", "Recognizing and reporting suspicious emails and links."),
        (
            "Password and Device Security",
            "Password managers, multi-factor authentication, and device encryption requirements.",
        ),
        ("Data Handling", "Classifying and handling confidential customer data."),
    ],
    OnboardingModule.Category.BENEFITS: [
        ("Health Insurance Enrollment", "Plan options, enrollment deadlines, and dependents."),
        ("Retirement Plan", "401k matching, vesting schedule, and contribution limits."),
    ],
    OnboardingModule.Category.CULTURE: [
        ("Company History and Values", "Founding story, mission, and the values behind decisions."),
        ("Communication Norms", "Slack etiquette, meeting culture, and async-first practices."),
    ],
}

TASK_CATALOG = [
    ("Set up laptop and accounts", "IT provisions hardware and creates accounts.", False),
    ("Submit signed offer letter", "HR files the countersigned offer letter.", True),
    ("Complete I-9 verification", "Manager confirms identity documents in person.", True),
    ("Add to payroll system", "Finance enters banking and tax withholding details.", True),
    ("Schedule 30-60-90 check-in", "Manager books recurring check-in meetings.", False),
    ("Order business cards", "Office manager orders cards for client-facing roles.", False),
    ("Grant building badge access", "Facilities issues a badge for office entry.", True),
    ("Assign onboarding buddy", "Manager pairs new hire with a peer mentor.", False),
]

SKILL_CATALOG = [
    (
        "Django ORM query optimization",
        "Diagnosing N+1 queries, choosing select_related versus prefetch_related, "
        "and reading query plans.",
    ),
    (
        "PostgreSQL indexing",
        "Designing composite and partial indexes, and reading EXPLAIN ANALYZE output.",
    ),
    (
        "Celery task design",
        "Structuring idempotent background tasks and retry and backoff strategies.",
    ),
    ("REST API design", "Structuring resource-oriented endpoints, pagination, and versioning."),
    (
        "Docker Compose environments",
        "Multi-service local development environments and volume management.",
    ),
    (
        "Vector search and embeddings",
        "Semantic search using sentence embeddings and approximate nearest neighbor indexes.",
    ),
    (
        "Redis caching strategy",
        "Cache invalidation, TTL tuning, and deciding what belongs in a cache.",
    ),
    ("JWT authentication", "Access and refresh token flows, rotation, and blacklisting."),
    ("Database migrations", "Writing safe, reversible schema migrations for a live database."),
    (
        "CI pipeline debugging",
        "Diagnosing flaky tests and service container failures in GitHub Actions.",
    ),
    (
        "Frontend accessibility review",
        "Auditing keyboard navigation, color contrast, and screen reader support.",
    ),
    ("Incident response", "Triage, communication, and postmortem practices during an outage."),
    ("Technical writing", "Documenting APIs and architectural decisions for other engineers."),
    (
        "Data pipeline debugging",
        "Tracing data quality issues through multi-stage ETL pipelines.",
    ),
    (
        "Load testing",
        "Designing realistic load tests and interpreting throughput and latency results.",
    ),
    (
        "Kubernetes troubleshooting",
        "Diagnosing pod crashes, resource limits, and networking issues.",
    ),
    ("SQL query tuning", "Rewriting slow queries and understanding query planner behavior."),
    (
        "Security code review",
        "Spotting injection, authentication, and access control issues in a diff.",
    ),
    (
        "Onboarding curriculum design",
        "Structuring training content and assessments for new hires.",
    ),
    (
        "Vendor contract review",
        "Reading SaaS contracts for data handling and liability terms.",
    ),
]


class Command(BaseCommand):
    help = "Seed the database with departments, users, modules, tasks, skills, and activity volume."

    def add_arguments(self, parser):
        parser.add_argument(
            "--events",
            type=int,
            default=1000,
            help="Number of ActivityEvent rows to generate.",
        )

    def handle(self, *args, **options):
        events_count = options["events"]
        fake = Faker()

        with transaction.atomic():
            self._clear_existing_data()
            departments = self._create_departments()
            users = self._create_users(fake, departments)
            modules = self._create_modules()
            tasks = self._create_tasks(departments)
            skills = self._create_skills()
            hire_dates = self._create_hire_dates(users)
            module_assignments = self._create_module_assignments(users, modules, hire_dates)
            task_assignments = self._create_task_assignments(users, tasks, hire_dates)
            user_skills = self._create_user_skills(users, skills)
            attempts_created = self._create_assessment_attempts(users, modules, hire_dates)
            events_created = self._bulk_create_in_batches(
                ActivityEvent,
                self._generate_activity_events(users, hire_dates, events_count),
                batch_size=BULK_BATCH_SIZE,
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {len(departments)} departments, {len(users)} users, "
                f"{len(modules)} modules, {len(tasks)} tasks, {len(skills)} skills, "
                f"{len(module_assignments)} module assignments, "
                f"{len(task_assignments)} task assignments, {len(user_skills)} user skills, "
                f"{attempts_created} assessment attempts, {events_created} activity events."
            )
        )

    def _clear_existing_data(self) -> None:
        # Deletion order matters. Rows behind an on_delete=PROTECT foreign key
        # (AssessmentAttempt.assessment, ModuleAssignment.module,
        # TaskAssignment.task) must go before the row they protect, or Django
        # raises ProtectedError partway through a reseed.
        ActivityEvent.objects.all().delete()
        AssessmentAttempt.objects.all().delete()
        TaskAssignment.objects.all().delete()
        ModuleAssignment.objects.all().delete()
        UserSkill.objects.all().delete()
        Skill.objects.all().delete()
        OnboardingTask.objects.all().delete()
        OnboardingModule.objects.all().delete()
        User.objects.filter(is_superuser=False).delete()
        Department.objects.all().delete()

    def _create_departments(self) -> list[Department]:
        return [Department.objects.create(name=name) for name in DEPARTMENT_NAMES]

    def _create_users(self, fake: Faker, departments: list[Department]) -> list[User]:
        seen_usernames = set()

        def unique_username() -> str:
            while True:
                candidate = fake.user_name()
                if candidate not in seen_usernames:
                    seen_usernames.add(candidate)
                    return candidate

        def create_user(manager: User | None) -> User:
            return User.objects.create_user(
                username=unique_username(),
                email=fake.unique.email(),
                password="onboarding-demo",
                first_name=fake.first_name(),
                last_name=fake.last_name(),
                department=random.choice(departments),
                manager=manager,
            )

        users = [create_user(manager=None) for _ in range(LEADERSHIP_COUNT)]

        for layer_size in LAYER_SIZES:
            eligible_managers = list(users)
            for _ in range(layer_size):
                users.append(create_user(manager=random.choice(eligible_managers)))

        return users

    def _create_modules(self) -> list[OnboardingModule]:
        modules = []
        order = 0
        for category, entries in MODULE_CATALOG.items():
            for title, description in entries:
                order += 1
                module = OnboardingModule.objects.create(
                    title=title,
                    description=description,
                    category=category,
                    order=order,
                )
                assessment = Assessment.objects.create(
                    module=module,
                    passing_score=random.choice([70, 75, 80, 85]),
                )
                for question_order, question_text in enumerate(self._questions_for(title), start=1):
                    AssessmentQuestion.objects.create(
                        assessment=assessment,
                        text=question_text,
                        order=question_order,
                    )
                modules.append(module)
        return modules

    def _questions_for(self, module_title: str) -> list[str]:
        return [
            f"What is the primary purpose of the {module_title} module?",
            f"Who should you contact with questions about {module_title}?",
            f"What is one action you are expected to take after completing {module_title}?",
        ]

    def _create_tasks(self, departments: list[Department]) -> list[OnboardingTask]:
        tasks = []
        for title, description, requires_approval in TASK_CATALOG:
            task = OnboardingTask.objects.create(
                title=title,
                description=description,
                requires_approval=requires_approval,
            )
            task.departments.set(random.sample(departments, k=random.randint(1, len(departments))))
            tasks.append(task)
        return tasks

    def _create_skills(self) -> list[Skill]:
        descriptions = [description for _, description in SKILL_CATALOG]
        embeddings = embed_texts(descriptions)
        return [
            Skill.objects.create(name=name, description=description, embedding=embedding)
            for (name, description), embedding in zip(SKILL_CATALOG, embeddings, strict=True)
        ]

    def _create_hire_dates(self, users: list[User]) -> dict[int, date]:
        today = timezone.localdate()
        return {
            user.id: today
            - timedelta(days=random.randint(HIRE_WINDOW_MIN_DAYS, HIRE_WINDOW_MAX_DAYS))
            for user in users
        }

    def _random_datetime_between(self, start: date, end: date) -> datetime:
        # end can land before start once due_date/hire_date arithmetic pushes
        # a window into the future relative to "today". Falling back to a
        # single-day window keeps every call valid instead of raising on a
        # negative randint range.
        if end <= start:
            end = start + timedelta(days=1)
        chosen_date = start + timedelta(days=random.randint(0, (end - start).days))
        chosen_time = time(hour=random.randint(7, 19), minute=random.randint(0, 59))
        return timezone.make_aware(datetime.combine(chosen_date, chosen_time))

    def _create_module_assignments(
        self,
        users: list[User],
        modules: list[OnboardingModule],
        hire_dates: dict[int, date],
    ) -> list[ModuleAssignment]:
        assignments = []
        for user in users:
            hire_date = hire_dates[user.id]
            for module in modules:
                due_date = hire_date + timedelta(days=7 * module.order)
                status = random.choices(
                    [
                        ModuleAssignment.Status.NOT_STARTED,
                        ModuleAssignment.Status.IN_PROGRESS,
                        ModuleAssignment.Status.COMPLETED,
                    ],
                    weights=[0.15, 0.25, 0.60],
                )[0]
                completed_at = None
                if status == ModuleAssignment.Status.COMPLETED:
                    completed_at = self._random_datetime_between(
                        hire_date, due_date + timedelta(days=5)
                    )
                assignments.append(
                    ModuleAssignment(
                        user=user,
                        module=module,
                        status=status,
                        due_date=due_date,
                        completed_at=completed_at,
                    )
                )
        ModuleAssignment.objects.bulk_create(assignments, batch_size=BULK_BATCH_SIZE)
        return assignments

    def _create_task_assignments(
        self,
        users: list[User],
        tasks: list[OnboardingTask],
        hire_dates: dict[int, date],
    ) -> list[TaskAssignment]:
        assignments = []
        for user in users:
            hire_date = hire_dates[user.id]
            window_end = hire_date + timedelta(days=30)
            for task in tasks:
                if task.requires_approval and user.manager_id is not None:
                    statuses = [
                        TaskAssignment.Status.PENDING,
                        TaskAssignment.Status.COMPLETED,
                        TaskAssignment.Status.APPROVED,
                    ]
                    weights = [0.20, 0.30, 0.50]
                else:
                    # No approval step to model, either because the task
                    # itself does not require one, or because a top-level
                    # user has no manager to approve it.
                    statuses = [TaskAssignment.Status.PENDING, TaskAssignment.Status.COMPLETED]
                    weights = [0.30, 0.70]

                status = random.choices(statuses, weights=weights)[0]
                completed_at = None
                approver = None
                approved_at = None
                if status in (TaskAssignment.Status.COMPLETED, TaskAssignment.Status.APPROVED):
                    completed_at = self._random_datetime_between(hire_date, window_end)
                if status == TaskAssignment.Status.APPROVED:
                    approver = user.manager
                    approved_at = self._random_datetime_between(completed_at.date(), window_end)

                assignments.append(
                    TaskAssignment(
                        task=task,
                        assignee=user,
                        approver=approver,
                        status=status,
                        completed_at=completed_at,
                        approved_at=approved_at,
                    )
                )
        TaskAssignment.objects.bulk_create(assignments, batch_size=BULK_BATCH_SIZE)
        return assignments

    def _create_user_skills(self, users: list[User], skills: list[Skill]) -> list[UserSkill]:
        proficiencies = [
            UserSkill.Proficiency.BEGINNER,
            UserSkill.Proficiency.INTERMEDIATE,
            UserSkill.Proficiency.EXPERT,
        ]
        user_skills = []
        for user in users:
            for skill in random.sample(skills, k=random.randint(2, 6)):
                user_skills.append(
                    UserSkill(
                        user=user,
                        skill=skill,
                        proficiency=random.choice(proficiencies),
                    )
                )
        UserSkill.objects.bulk_create(user_skills, batch_size=BULK_BATCH_SIZE)
        return user_skills

    def _create_assessment_attempts(
        self,
        users: list[User],
        modules: list[OnboardingModule],
        hire_dates: dict[int, date],
    ) -> int:
        assessments_by_module_id = {
            assessment.module_id: assessment for assessment in Assessment.objects.all()
        }

        def attempts_for(user: User, module: OnboardingModule) -> Iterator[AssessmentAttempt]:
            assessment = assessments_by_module_id[module.id]
            passing_score = assessment.passing_score
            attempt_count = random.choices([1, 2, 3], weights=[0.65, 0.25, 0.10])[0]
            eventual_pass = random.random() < 0.85
            attempt_window_start = hire_dates[user.id] + timedelta(days=7 * module.order)

            for attempt_index in range(attempt_count):
                is_final_attempt = attempt_index == attempt_count - 1
                if is_final_attempt and eventual_pass:
                    score = random.randint(passing_score, 100)
                else:
                    score = random.randint(0, max(passing_score - 1, 0))

                window_start = attempt_window_start + timedelta(days=3 * attempt_index)
                window_end = window_start + timedelta(days=2)
                yield AssessmentAttempt(
                    user=user,
                    assessment=assessment,
                    score=score,
                    attempted_at=self._random_datetime_between(window_start, window_end),
                )

        def all_attempts() -> Iterator[AssessmentAttempt]:
            for user in users:
                for module in modules:
                    yield from attempts_for(user, module)

        return self._bulk_create_in_batches(
            AssessmentAttempt, all_attempts(), batch_size=BULK_BATCH_SIZE
        )

    def _generate_activity_events(
        self,
        users: list[User],
        hire_dates: dict[int, date],
        count: int,
    ) -> Iterator[ActivityEvent]:
        today = timezone.localdate()
        for _ in range(count):
            user = random.choice(users)
            yield ActivityEvent(
                user=user,
                event_type=random.choice(EVENT_TYPES),
                metadata={"source": "seed_data"},
                occurred_at=self._random_datetime_between(hire_dates[user.id], today),
            )

    def _bulk_create_in_batches(self, model, objects: Iterator, batch_size: int) -> int:
        # objects is a generator, not a list. Chunking it manually here means
        # only one batch_size worth of model instances ever exists in Python
        # memory at a time, regardless of how large --events gets. Passing
        # batch_size to bulk_create itself is a separate concern: it caps how
        # many rows go into a single INSERT statement, which is what keeps a
        # 100,000-row call from either becoming 100,000 round trips or one
        # statement wide enough to hit Postgres's parameter limit.
        total = 0
        batch = []
        for obj in objects:
            batch.append(obj)
            if len(batch) >= batch_size:
                model.objects.bulk_create(batch, batch_size=batch_size)
                total += len(batch)
                batch = []
        if batch:
            model.objects.bulk_create(batch, batch_size=batch_size)
            total += len(batch)
        return total
