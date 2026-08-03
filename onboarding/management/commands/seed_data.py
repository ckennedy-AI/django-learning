import random

from django.core.management.base import BaseCommand
from django.db import transaction
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
LEADERSHIP_COUNT = 2
LAYER_SIZES = [6, 14, 20]

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

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {len(departments)} departments, {len(users)} users, "
                f"{len(modules)} modules, {len(tasks)} tasks, {len(skills)} skills."
            )
        )
        self.stdout.write(
            self.style.WARNING(
                f"--events={events_count} requested. Assignments, assessment attempts, "
                "and activity events are generated by the next pass of this command."
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
