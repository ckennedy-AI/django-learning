# CLAUDE.md

Context and conventions for this repository. Read this before generating any code.

## What this project is

An internal employee onboarding platform, backend only. New hires are assigned onboarding modules covering company policy, security awareness, benefits, and culture, each with a short assessment. They also receive non-learning onboarding tasks that require manager approval. A company directory tracks departments and reporting relationships, and a skills directory is searchable by meaning so an employee can find help from a vague problem description.

**This is a learning project.** It exists so the repository owner can build foundational Django knowledge before working on RuroTech's production app, RigAgent. It is not going to production. Correctness and comprehensibility matter more than cleverness or brevity.

**Consequence for you:** every response that produces code must also explain what the code does and why you chose that approach. Do not wait to be asked. If a prompt says "add X," produce X and then explain the mechanism, the tradeoff you made, and where it could go wrong. Code without explanation is a failed response in this repo.

## Companion files in this repo root

- `project-checklist.md` is the requirements document. Twelve checklists of features and tasks. If a prompt references a checklist item, this is where it comes from.
- `django-learning-roadmap.md` is the build order, with fourteen phases, resources, and comprehension checks. It also documents which endpoints and Celery tasks are planned and why.
- `django-styleguide.md` is the HackSoft Django Styleguide, which is the architectural spec for this project. When a convention below is unclear, this file is the authority.

Read the relevant sections of these rather than guessing at project intent.

## Stack

| Component | Choice |
|---|---|
| Framework | Django 6.0 |
| API layer | Django REST Framework |
| Database | PostgreSQL 17 with pgvector |
| Cache and broker | Redis |
| Background jobs | Celery, with Celery Beat and Flower |
| Embeddings | sentence-transformers, `all-MiniLM-L6-v2`, 384 dimensions, CPU only |
| Environment | Docker Compose |
| Config | django-environ, with `env.db()` and `env.cache()` |
| Auth | djangorestframework-simplejwt |
| CI | GitHub Actions |
| Lint and format | Ruff |

Development happens on Windows in PowerShell. All Django commands run inside the container.

## Architecture rules

These are non-negotiable. They come from the repository owner's supervisor and from the HackSoft styleguide. Do not violate them, and if a prompt asks for something that would, say so before writing code.

### Layering

- **Plain DRF `APIView` only.** Never `ModelViewSet`. Never DRF generics (`ListAPIView`, `RetrieveAPIView`, and so on). Never routers.
- **Reads go in `selectors.py`.** Writes and business logic go in `services.py`.
- **Views do three things:** request handling, input validation, and response shaping. Nothing else.
- **No ORM access in views.** No ORM access in serializers. Not a single `.objects` call outside `selectors.py`, `services.py`, model methods, or management commands.
- **No business logic in serializers, signals, or model `save()`.**
- Custom managers and querysets are for reusable query filters, not for business logic.

### APIs and serializers

- One API class per operation. One URL per action.
- Naming convention is `<Entity><Action>Api`: `ModuleListApi`, `ModuleDetailApi`, `TaskApprovalApi`, `MyDashboardApi`.
- Serializers are nested inside the API class as `InputSerializer` and `OutputSerializer`.
- `InputSerializer` is always a plain `serializers.Serializer`. `OutputSerializer` may subclass `ModelSerializer`.
- Reuse serializers as little as possible. A shared serializer that changes for one endpoint breaks the others silently. Use an `inline_serializer` helper for nesting rather than importing another API's serializer.
- URLs are named, grouped into per-domain pattern lists, and included from `urlpatterns`. Reference URLs by name, never by hardcoded path.

### Validation

- Simple, non-relational, multi-field validation goes in the model's `clean`, invoked through `full_clean()` in the service before save.
- Complex validation, or validation that spans relations or fetches data, goes in the service.
- Prefer a database constraint wherever one is possible. Less code to maintain, and the data is protected regardless of what wrote it.

### Writes

- Multi-step writes are wrapped in `transaction.atomic`.
- Application errors raise a custom `ApplicationError`, translated to an HTTP status in exactly one place via a custom DRF exception handler. Do not scatter `Response(status=400)` through services.

## Performance rules

Performance is a first-class requirement here, not a later cleanup pass. Every one of these is a decision made while writing the endpoint.

- **One endpoint per data need.** Never one bulky endpoint driven by many optional filter parameters. Separate list from detail. Separate different slices of the same model into separate endpoints, for example the full user object versus that user's skills versus that user's direct reports.
- **Return only the fields the endpoint needs.** Do not serialize related data the caller did not ask for.
- **`select_related` and `prefetch_related` are chosen per endpoint, deliberately.** Do not apply them by reflex, and do not apply them to a queryset whose related fields the serializer never touches.
- **Every list endpoint is paginated.** DRF pagination does not apply automatically to plain `APIView`, so it goes through a `get_paginated_response` helper in `api/pagination.py`.
- **Filter parameters are validated by a nested `FilterSerializer` on the API class. The actual filtering happens inside the selector.**
- **Be cautious with many-to-many reads.** Measure the query cost before exposing one through an endpoint.
- **Optimize according to expected traffic.** A dashboard endpoint hit on every page load gets tuned tightly and cached. A report an admin runs monthly does not need micro-optimization, and leaving it plain is a deliberate, documented choice.
- **Benchmark before and after.** Never assert an optimization helped without measuring it. `defer()` and `only()` in particular become a pessimization if a deferred field is later accessed.
- When you write or change an endpoint, state its expected query count and flag any N+1 risk in your explanation.

## Migrations

- `makemigrations` for every schema change. Do not hand-write migrations.
- **The single exception** is the pgvector extension migration, created with `makemigrations <app> --empty --name enable_pgvector` and given a `VectorExtension()` operation. It must run before any migration that creates a vector column.
- Never edit an applied migration. Add a new one.

## Known gotchas

Assume these are true. Do not reintroduce them.

1. **The Postgres image must be `pgvector/pgvector:pg17`.** The stock `postgres:17` image has no vector extension binary. This applies to both `docker-compose.yml` and the GitHub Actions service container. Do not suggest the runner's preinstalled Postgres or swapping to SQLite in CI, because both break pgvector.
2. **Celery tasks are enqueued with `transaction.on_commit`,** never a bare `.delay()` inside an `atomic` block. A worker is a separate process with its own connection and will read a row that has not committed yet.
3. **Pass IDs to Celery tasks, never model instances.**
4. **DRF pagination and filter backends do not apply to plain `APIView`.** See the performance rules above.
5. **Django's `TestCase` rolls back its transaction, so `on_commit` callbacks never fire.** Tests covering task enqueueing need `captureOnCommitCallbacks(execute=True)`.
6. **Django Debug Toolbar does not render on JSON responses.** Use `assertNumQueries` and `connection.queries` for query auditing. Configure the toolbar with `debug_toolbar.middleware.show_toolbar_with_docker` as the `SHOW_TOOLBAR_CALLBACK`, not the `socket.gethostbyname_ex` hack, and do not enable it during tests.
7. **Django has a built-in Redis cache backend since 4.0.** Use `django.core.cache.backends.redis.RedisCache`. Do not suggest django-redis.
8. **Embedding dimension is baked into the database column.** 384 for `all-MiniLM-L6-v2`. Changing providers is a migration plus a re-embed, not a config change.
9. **Simple JWT's `SIGNING_KEY` comes from its own environment variable,** not `SECRET_KEY`.
10. **`ROTATE_REFRESH_TOKENS` and `BLACKLIST_AFTER_ROTATION` are two settings,** and the latter does nothing unless the former is True and `rest_framework_simplejwt.token_blacklist` is in `INSTALLED_APPS`.

## Intended file layout

```
config/
  settings.py
  urls.py
  celery.py
  wsgi.py
  asgi.py
api/
  pagination.py          # get_paginated_response helper
  exception_handlers.py  # custom DRF exception handler
  utils.py               # inline_serializer helper
core/
  exceptions.py          # ApplicationError
onboarding/
  models.py
  admin.py
  apis.py
  selectors.py
  services.py
  tasks.py
  urls.py
  embeddings.py          # embed_texts provider function
  management/commands/seed_data.py
  tests/
```

Keep `apis.py`, `selectors.py`, and `services.py` as flat modules until one of them gets unwieldy, then split by sub-domain into a package.

## Schema

Twelve models. This section is the intent; `onboarding/models.py` is the truth once it exists. If they disagree, read the models file and tell the repository owner this section is stale.

| Model | Notes |
|---|---|
| `User` | Custom, subclasses `AbstractUser`. Self-referential FK `manager`. FK `department`. `AUTH_USER_MODEL` must be set before the first migration. |
| `Department` | Org units. |
| `OnboardingModule` | Policy, security, benefits, culture content. Category choices, explicit ordering. |
| `ModuleAssignment` | FK to `User` and `OnboardingModule`. Status choices, `due_date`, `completed_at`. Property deriving overdue state. |
| `Assessment` | `OneToOneField` to `OnboardingModule`. Passing score. |
| `AssessmentQuestion` | FK to `Assessment`, ordered. |
| `AssessmentAttempt` | Volume table, several thousand rows. Check constraint keeping score between 0 and 100. |
| `OnboardingTask` | Non-learning tasks. `ManyToManyField` to `Department`. |
| `TaskAssignment` | Two FKs to `User`, one for the assignee and one for the approver. Approval is a transactional multi-model write. |
| `Skill` | `VectorField(dimensions=384)` for the embedding, with an `HnswIndex` using `opclasses=['vector_cosine_ops']`. |
| `UserSkill` | Explicit through model for `User` to `Skill`. Unique constraint on the pair. This is the many-to-many whose read cost gets measured. |
| `ActivityEvent` | Primary volume table, 100,000+ rows. `JSONField` for metadata. Composite index on `user` and `occurred_at` descending. `occurred_at` is set once on creation, non-null, and effectively unique, which makes it the cursor pagination key. |

Every model gets `__str__`, `Meta.ordering`, `related_name` on every relationship, and a deliberate `on_delete` you can justify.

## Endpoints

Fill in the last two columns as each endpoint is built. This table is the deliverable for the checklist item about recording expected usage volume and the optimization level it justifies.

| Endpoint | Purpose | Expected traffic | Optimization level | Query count |
|---|---|---|---|---|
| `ModuleListApi` | All onboarding modules, paginated | | | |
| `ModuleDetailApi` | One module by id | | | |
| `MyDashboardApi` | Current user's assignments, pending tasks, completion percentage | High, every page load | Tight. Cached in Redis, minimum queries | |
| `ActivityEventListApi` | Activity feed, cursor paginated | | | |
| `UserDetailApi` | Full user object | | | |
| `UserSkillsApi` | One user's skills, its own endpoint rather than a filter parameter | | | |
| `UserReportsApi` | Direct manager and direct reports only | | | |
| `SkillSearchApi` | Vector similarity search over skill descriptions | | | |
| `TaskApprovalApi` | POST. Approves a task assignment and records an activity event in one transaction | | | |
| `DepartmentActivityReportApi` | Department-wide report | Low, occasional admin use | Deliberately unoptimized. Document the tradeoff | |

Authorization rule worth stating explicitly: on `TaskApprovalApi`, a manager may approve their own direct reports' tasks and nobody else's. That is an object-level permission check, and the per-user query scoping that supports it belongs in the selector, not duplicated in the permission class.

## Celery tasks

| Task | Trigger | Notes |
|---|---|---|
| `generate_skill_embedding(skill_id)` | Service, on skill create or description change | The slow operation moved out of the request cycle. Enqueue with `transaction.on_commit`. |
| `score_assessment_attempt(attempt_id)` | Service, on attempt submit | Must be idempotent. Running it twice produces the same result. |
| `send_overdue_reminders()` | Beat | Retries with exponential backoff, since notification sends fail transiently. |
| `rollup_department_progress()` | Beat, nightly | Periodic aggregation. Candidate for a dedicated queue. |

Tasks are thin. A task fetches what it needs by ID and calls a service. Business logic lives in the service, not the task. Import the service inside the task function body to avoid circular imports, and import the task at module level with a `_task` suffix where a service triggers it.

## Commands

```powershell
docker compose up
docker compose down
docker compose up --build

docker compose exec web python manage.py migrate
docker compose exec web python manage.py makemigrations
docker compose exec web python manage.py shell
docker compose exec web python manage.py seed_data --events 100000
docker compose exec web python manage.py test

docker compose exec db psql -U postgres -d onboarding

docker compose logs -f celery-worker
```

## Style

- **No em-dashes anywhere.** Not in code comments, not in docstrings, not in documentation, not in generated seed data. Use commas, colons, or separate sentences.
- Type-annotate service and selector functions.
- Service and selector functions take keyword-only arguments unless they take zero or one argument.
- Service naming follows `<entity>_<action>`: `task_approve`, `skill_create`. Selector naming follows the same pattern: `module_list`, `user_dashboard_get`.
- Ruff for linting and formatting. Do not hand-format around it.

## How to work in this repo

- Prompts here are narrowly scoped on purpose, usually one checklist item at a time. Do not expand scope. If a prompt asks for one endpoint, do not also build three related ones.
- If a prompt is ambiguous, ask one question rather than guessing across several assumptions.
- If you are uncertain whether something is accurate for Django 6.0 or for this specific setup, say so and name what to check. A confident wrong answer costs more time here than an honest uncertain one.
- If a prompt would violate a convention in this file, say which convention and why before writing anything.
- Prefer pointing at the canonical documentation page over reproducing its content.
- When you touch the schema, the endpoint list, or the task list, update the corresponding table in this file in the same change.
