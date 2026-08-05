# CLAUDE.md

Context and conventions for this repository. Read this before generating any code.

## What this project is

An internal employee onboarding platform, backend only. New hires are assigned onboarding modules covering company policy, security awareness, benefits, and culture, each with a short assessment. They also receive non-learning onboarding tasks that require manager approval. A company directory tracks departments and reporting relationships, and a skills directory is searchable by meaning so an employee can find help from a vague problem description.

**This is a learning project.** It exists so the repository owner can build foundational Django knowledge before working on RuroTech's production app, RigAgent. It is not going to production. Correctness and comprehensibility matter more than cleverness or brevity.

**Consequence for you:** every response that produces code must also explain what the code does and why you chose that approach. Do not wait to be asked. If a prompt says "add X," produce X and then explain the mechanism, the tradeoff you made, and where it could go wrong. Code without explanation is a failed response in this repo.

**Explain the path, not just the file.** When you touch an endpoint, a service, or a task, trace the full flow in your explanation: URL resolution, view, permission check, selector or service, model and SQL, response shaping, and anything that happens outside the request cycle such as a Celery enqueue or a cache invalidation. Naming which layer owns each decision matters more here than describing the internals of any one function. The point of this project is that the repository owner can trace a reported bug through the whole system before asking for help.

## Companion files in this repo root

- `project-checklist.md` is the requirements document. Twelve checklists of features and tasks. If a prompt references a checklist item, this is where it comes from.
- `django-learning-roadmap.md` is the build order, with fourteen phases, resources, and comprehension checks. It also documents which endpoints and Celery tasks are planned and why.
- `django-styleguide.md` is the HackSoft Django Styleguide, which is the architectural spec for this project. When a convention below is unclear, this file is the authority, except where this file records a deliberate deviation.

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
| Lint and format | Ruff, configured in `pyproject.toml` |

Development happens on Windows in PowerShell. All Django commands run inside the container.

## Architecture rules

These are non-negotiable. They come from the repository owner's supervisor and from the HackSoft styleguide. Do not violate them, and if a prompt asks for something that would, say so before writing code.

### Layering

- **Plain DRF `APIView` only.** Never `ModelViewSet`. Never DRF generics (`ListAPIView`, `RetrieveAPIView`, and so on). Never routers.
- **Reads go in `selectors/`. Writes and business logic go in `services/`.**
- **Views do three things:** request handling, input validation, and response shaping. Nothing else.
- **No ORM access in views.** No ORM access in serializers. No ORM access in permission classes. Not a single `.objects` call outside `selectors/`, `services/`, model methods and managers, or management commands.
- **No business logic in serializers, signals, or model `save()`.**
- Custom managers and querysets are for reusable query filters, not for business logic.

### Direction of dependency

Layers may only call downward. This is what makes a bug traceable in one direction rather than two.

- Views call services, selectors, and permission classes.
- Services call selectors, other services, models, and enqueue tasks.
- Selectors call other selectors and models. **A selector never calls a service.** If a read appears to need a write, the write belongs in the service that called the selector.
- Celery tasks call services. Tasks contain no business logic.
- Models know nothing about any layer above them.

## Module structure

**Layers that will keep growing are packages. Layers that stay short are flat files.**

Packages, one module per sub-domain, each with an `__init__.py` that re-exports its public names:

- `onboarding/models/`
- `onboarding/views/`
- `onboarding/selectors/`
- `onboarding/services/`
- `onboarding/tests/`

Flat files, promoted to a package only when one of them passes roughly 300 lines or covers more than about three sub-domains:

- `onboarding/admin.py`
- `onboarding/permissions.py`
- `onboarding/tasks.py`
- `onboarding/urls.py`
- `onboarding/embeddings.py`

### The sub-domain vocabulary

The same sub-domain names are used in every package, so that finding an endpoint tells you the filename to open in every other layer. This is the whole reason for the package structure, so the naming is fixed rather than per-layer.

| Sub-domain module | Models it owns | Endpoints it owns |
|---|---|---|
| `users` | `User` | `UserDetailApi`, `UserSkillsApi`, `UserReportsApi` |
| `departments` | `Department` | `DepartmentActivityReportApi` |
| `modules` | `OnboardingModule`, `ModuleAssignment` | `ModuleListApi`, `ModuleDetailApi` |
| `assessments` | `Assessment`, `AssessmentQuestion`, `AssessmentAttempt` | none yet |
| `onboarding_tasks` | `OnboardingTask`, `TaskAssignment` | `TaskApprovalApi` |
| `skills` | `Skill`, `UserSkill` | `SkillSearchApi` |
| `activity` | `ActivityEvent` | `ActivityEventListApi` |
| `dashboard` | none, it is a cross-domain read | `MyDashboardApi` |

Rules for placement:

- **An API class goes in the module named for the `<Entity>` in `<Entity><Action>Api`.** `UserSkillsApi` is a user endpoint, so it lives in `views/users.py`, even though its selector reads `UserSkill`. This is a mechanical rule on purpose, so placement is never a judgement call.
- A selector or service goes in the module named for the entity it primarily reads or writes. A service that spans sub-domains goes with the entity that owns the outcome. `task_approve` writes an `ActivityEvent` but its outcome is an approved `TaskAssignment`, so it lives in `services/onboarding_tasks.py`.
- **Create a module only when that sub-domain has content in that layer.** An empty `services/activity.py` is worse than no file. `assessments` has no endpoints yet, so it has no `views/assessments.py`.
- `onboarding_tasks` is named that way, not `tasks`, to keep it unambiguous against `onboarding/tasks.py`, which holds Celery tasks and nothing else.

### Package import conventions

- Each `__init__.py` re-exports the public names from its submodules, so import paths outside the package do not change: `from onboarding.selectors import module_list`, not `from onboarding.selectors.modules import module_list`.
- `models/__init__.py` re-exporting every model is not optional, it is how Django discovers them. See gotcha 14.
- Within a package, import from the sibling submodule directly.
- If two model submodules reference each other, break the cycle with a string reference (`models.ForeignKey("onboarding.Department", ...)`) rather than reordering imports.

### APIs and serializers

- One API class per operation. One URL per action.
- Naming convention is `<Entity><Action>Api`: `ModuleListApi`, `ModuleDetailApi`, `TaskApprovalApi`, `MyDashboardApi`.
- Serializers are nested inside the API class as `InputSerializer` and `OutputSerializer`.
- `InputSerializer` is always a plain `serializers.Serializer`. `OutputSerializer` may subclass `ModelSerializer`.
- Reuse serializers as little as possible. A shared serializer that changes for one endpoint breaks the others silently. Use an `inline_serializer` helper for nesting rather than importing another API's serializer.
- URLs are named, grouped into per-domain pattern lists, and included from `urlpatterns`. Reference URLs by name, never by hardcoded path.

### HTTP method semantics

The method is part of the contract a React client depends on, so it is chosen deliberately rather than defaulted.

- `GET` reads and has no side effects.
- `POST` creates a resource, or performs a named action that is not a plain field update. `TaskApprovalApi` is the latter.
- `PUT` replaces a resource in full. Every writable field is required, and a field the caller omits is set to its default or null rather than left alone.
- `PATCH` updates part of a resource. Every `InputSerializer` field is `required=False`, and only the fields present in the request body are written. A `PATCH` handler that writes a field the caller did not send is a bug. An empty `PATCH` body returns 400 rather than a 200 that did nothing.
- `DELETE` removes a resource. Prefer a status field or soft delete over a hard delete where the row is referenced by `ActivityEvent`.
- **Deviation from HackSoft:** the styleguide's `CourseUpdateApi` example uses `post` for updates. This repo uses `PATCH` and `PUT` with the semantics above. Flagged as a deviation so it is a decision rather than drift.

### Validation

- Simple, non-relational, multi-field validation goes in the model's `clean`, invoked through `full_clean()` in the service before save.
- Complex validation, or validation that spans relations or fetches data, goes in the service.
- Prefer a database constraint wherever one is possible. Less code to maintain, and the data is protected regardless of what wrote it.

**How invalid input is handled: 4xx, not a safe default.** Every API validates its query parameters or body through a nested serializer and calls `is_valid(raise_exception=True)`. A missing or malformed parameter is a client bug, and quietly substituting a default would return a plausible-looking response to a question the caller never asked, which is the harder failure to debug of the two. The specifics:

- A failed serializer returns 400. The single handler in `api/exception_handlers.py` normalises every error, DRF-native or not, to `{"message": ..., "extra": {...}}`, with the offending field names under `extra.fields` for validation errors.
- A default is only ever applied where a serializer field declares one, which makes it part of the published contract rather than a guess. `SkillSearchApi.limit` defaulting to 10 is the only such case today.
- Any parameter that bounds a result set carries an explicit upper bound. `SkillSearchApi.limit` is `max_value=50` and is rejected above that. Note the deliberate inconsistency: DRF's own `LimitOffsetPagination` silently clamps `?limit=` to `max_limit` instead of erroring. That is DRF's behaviour rather than a choice made here, and it is not worth overriding, but it is worth knowing which of the two you are talking to.
- A lookup that finds nothing returns 404, in the same envelope. Where a lookup is scoped to enforce a permission, as in `TaskApprovalApi`, the 404 is the point: it does not distinguish "not yours" from "does not exist".
- `ApplicationError` raised by a service is the one exception DRF's handler does not recognise, so it is translated to 400 explicitly in the same place.

These are locked in by `InvalidInputTests` in the view tests under `onboarding/tests/views/`, so the documented behaviour and the actual behaviour cannot drift apart silently.

### Writes

- Multi-step writes are wrapped in `transaction.atomic`.
- Application errors raise a custom `ApplicationError`, translated to an HTTP status in exactly one place via a custom DRF exception handler. Do not scatter `Response(status=400)` through services.

## Permissions and authorization

Authorization is two separate questions, answered in two different layers. Conflating them is the failure mode to avoid, because a permission class that correctly lets a caller through says nothing about which rows the selector then hands back.

**Question one: may this caller invoke this endpoint at all?** Answered by DRF authentication and permission classes. `IsAuthenticated` is the project default, set once in the `REST_FRAMEWORK` settings. Endpoint-specific classes live in `onboarding/permissions.py`. A permission class answers yes or no about the caller, and for an object-level check, about one already-fetched object. It does not run queries to find rows.

**Question two: which rows may this caller see or change?** Answered by query scoping inside the selector. A selector whose answer depends on who is asking takes the requesting user as a keyword argument and applies the scope itself.

Rules:

- **Every endpoint has an entry in the permissions table below, answering both questions.** An endpoint with a blank entry is not finished.
- **Row scoping belongs in the selector, never duplicated in a permission class and never done in the view.** If two endpoints need the same scope, extract a scoping selector and call it from both, the way HackSoft's `user_list` calls `user_get_visible_for`.
- **Roles in this project are derived from existing fields, not from a role column.** Self is `request.user.id == target user id`. Manager is `target.manager_id == request.user.id`. Staff is `request.user.is_staff`, inherited from `AbstractUser`. There is no role field on `User`, so do not assume one. Adding one is a schema change and a migration, and it needs a conversation first.
- **Choose 404 or 403 deliberately.** Prefer a scoped lookup that 404s where the existence of the row is itself information the caller should not have, as `TaskApprovalApi` already does. Use an explicit 403 where the caller may legitimately know the object exists but may not act on it. Say which one you chose and why.
- **Object-level checks are not automatic on plain `APIView`.** See gotcha 15.
- A write endpoint states, in the same explanation as the code, who may write and what the response is on a scope violation.

### Permissions table

Most of this column is intent until Phase 10 lands JWT auth. Rows marked **OPEN** are known holes that exist because there is no `request.user` yet, and closing them is Phase 10 work, not a bug to fix opportunistically.

| Endpoint | May call | Row scope | State |
|---|---|---|---|
| `ModuleListApi` | `IsAuthenticated` | Unscoped. The module catalogue is the same for every employee | Intent |
| `ModuleDetailApi` | `IsAuthenticated` | Unscoped | Intent |
| `MyDashboardApi` | `IsAuthenticated` | `request.user` only, always. There is no legitimate caller for someone else's dashboard | **OPEN.** Takes `user_id` as a query parameter today, so any caller can read any user's dashboard. Phase 10 drops the parameter and reads `request.user`, which also changes the cache key |
| `ActivityEventListApi` | `IsAuthenticated` | Self by default. A manager may filter to a direct report. Staff unrestricted | **OPEN.** `user_id` is an unscoped filter parameter today |
| `UserDetailApi` | `IsAuthenticated` | Unscoped read of the directory. Decide during Phase 10 whether any field needs trimming for non-staff callers | Intent |
| `UserSkillsApi` | `IsAuthenticated` | Unscoped read | Intent |
| `UserReportsApi` | `IsAuthenticated` | Unscoped read | Intent |
| `SkillSearchApi` | `IsAuthenticated` | Unscoped | Intent |
| `TaskApprovalApi` | `IsAuthenticated`, plus an object-level manager check | `assignee__manager_id == request.user.id`, applied in the selector. Violation returns 404, not 403 | Scope implemented. Permission class pending Phase 10 |
| `DepartmentActivityReportApi` | Staff only | Unscoped once the caller is staff | Intent |

## Performance rules

Performance is a first-class requirement here, not a later cleanup pass. Every one of these is a decision made while writing the endpoint.

- **One endpoint per data need.** Never one bulky endpoint driven by many optional filter parameters. Separate list from detail. Separate different slices of the same model into separate endpoints, for example the full user object versus that user's skills versus that user's direct reports.
- **Return only the fields the endpoint needs.** Do not serialize related data the caller did not ask for.
- **`select_related` and `prefetch_related` are chosen per endpoint, deliberately.** Do not apply them by reflex, and do not apply them to a queryset whose related fields the serializer never touches.
- **Every list endpoint is paginated.** DRF pagination does not apply automatically to plain `APIView`, so it goes through a `get_paginated_response` helper in `api/pagination.py`. Two endpoints are documented exceptions, and the reasoning is recorded on the class and in the endpoint table rather than left implicit: `SkillSearchApi` is already bounded by a validated `limit`, and `DepartmentActivityReportApi` returns a list its selector has already fully materialised, bounded by department count. An exception has to be argued for; silence is not an exception.
- **An index is justified by a plan, not by intuition.** Add or adjust indexes based on the filters the endpoints actually accept, then read the `EXPLAIN ANALYZE` output to confirm the planner chooses them. An index that exists is not an index that gets used, and on a small table the planner is right to ignore one. `manage.py explain_queries` prints the plan for every filtered access path an endpoint exposes.
- **Filter parameters are validated by a nested `FilterSerializer` on the API class. The actual filtering happens inside the selector.**
- **Be cautious with many-to-many reads.** Measure the query cost before exposing one through an endpoint.
- **Optimize according to expected traffic.** A dashboard endpoint hit on every page load gets tuned tightly and cached. A report an admin runs monthly does not need micro-optimization, and leaving it plain is a deliberate, documented choice.
- **Benchmark before and after.** Never assert an optimization helped without measuring it. `defer()` and `only()` in particular become a pessimization if a deferred field is later accessed.
- When you write or change an endpoint, state its expected query count and flag any N+1 risk in your explanation.
- **Adding a permission scope changes the query.** A selector that gains a `requesting_user` filter gains a `WHERE` clause, which may need an index it did not need before. Re-check the plan rather than assuming the scope is free.

## Migrations

- `makemigrations` for every schema change. Do not hand-write migrations.
- **The single exception** is the pgvector extension migration, created with `makemigrations <app> --empty --name enable_pgvector` and given a `VectorExtension()` operation. It must run before any migration that creates a vector column.
- Never edit an applied migration. Add a new one.
- **Moving a model between modules inside the same app is not a schema change and must not generate a migration.** Django identifies a model by app label and class name, not by module path. If `makemigrations --check --dry-run` reports changes after a pure file move, something is wrong. See gotcha 14.

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
11. **`torch` must be installed from PyTorch's CPU index inside the container.** On Linux the default PyPI `torch` wheel hard-depends on the `nvidia-cu13` CUDA runtime packages, which add several GB to an image that runs embeddings on CPU only. `requirements.txt` was frozen on Windows, where the default wheel is already CPU-only, so the pin looks harmless and is not. The Dockerfile sets `--index-url https://download.pytorch.org/whl/cpu` with PyPI as `--extra-index-url`. Do not simplify that back to a plain `pip install -r requirements.txt`.
12. **`AUTH_USER_MODEL` must be set before the first `migrate`.** If the auth and admin migrations are already applied against the default `auth.User`, introducing the custom user model fails with `InconsistentMigrationHistory` or a lazy-reference `ValueError` on `admin.LogEntry.user`. The fix during development is `docker compose down -v` to drop the database volume, not a hand-written migration. See `docs/docker.md`.
13. **The host virtual environment cannot run this project.** `DATABASE_URL` and `REDIS_URL` point at the Compose service names `db` and `redis`, which do not resolve on the host. The host `.venv` is for editor tooling only, and it is on a different Python version than the container.
14. **A model that is not imported in `models/__init__.py` is invisible to Django's app registry, and `makemigrations` will generate a `DeleteModel` for it.** This is the sharpest edge in the package layout: the failure looks like a schema change rather than a missing import. After touching anything under `models/`, run `makemigrations --check --dry-run` and expect no changes.
15. **`check_object_permissions` is not called automatically on a plain `APIView`.** DRF calls `check_permissions` in `initial()`, so `has_permission` runs on every request, but `has_object_permission` only runs where `GenericAPIView.get_object()` would have called it. On these API classes it has to be invoked explicitly after fetching the object. This is the same shape of problem as gotcha 4: the convenience lives in the generics this project does not use.

## File layout

```
config/
  settings.py
  urls.py
  celery.py
  wsgi.py
  asgi.py
api/
  pagination.py            # get_paginated_response helper
  exception_handlers.py    # custom DRF exception handler
  utils.py                 # inline_serializer helper
core/
  exceptions.py            # ApplicationError
onboarding/
  models/
    __init__.py            # re-exports every model, required for app registry
    users.py
    departments.py
    modules.py
    assessments.py
    onboarding_tasks.py
    skills.py
    activity.py
  views/
    __init__.py
    users.py
    departments.py
    modules.py
    onboarding_tasks.py
    skills.py
    activity.py
    dashboard.py
  selectors/
    __init__.py            # mirrors views, one module per sub-domain with reads
  services/
    __init__.py            # mirrors views, one module per sub-domain with writes
  tests/
    __init__.py
    models/
    selectors/
    services/
    views/
  admin.py
  permissions.py           # DRF permission classes, created in Phase 10
  tasks.py                 # Celery tasks only
  urls.py
  embeddings.py            # embed_texts provider function
  management/commands/
```

Tests are organised by layer first and sub-domain second, following HackSoft: `tests/selectors/test_modules.py` holds the tests for `selectors/modules.py`. The file naming convention is `test_<module_name>.py` and the test case naming convention is `class <ThingUnderTest>Tests(TestCase)`.

**Deviation from HackSoft on naming:** the styleguide names the API layer `apis.py`. This repo names it `views/` instead, to match the repository owner's company convention. This is deliberate, not drift. Every other HackSoft convention still applies: plain `APIView` classes, `<Entity><Action>Api` naming, `InputSerializer` and `OutputSerializer` nested inside each class. Only the name differs.

## Schema

Twelve models. This section is the intent; `onboarding/models/` is the truth. If they disagree, read the models package and tell the repository owner this section is stale.

| Model | Module | Notes |
|---|---|---|
| `User` | `users` | Custom, subclasses `AbstractUser`. Self-referential FK `manager`. FK `department`. `AUTH_USER_MODEL` must be set before the first migration. |
| `Department` | `departments` | Org units. |
| `OnboardingModule` | `modules` | Policy, security, benefits, culture content. Category choices, explicit ordering. |
| `ModuleAssignment` | `modules` | FK to `User` and `OnboardingModule`. Status choices, `due_date`, `completed_at`. Property deriving overdue state. |
| `Assessment` | `assessments` | `OneToOneField` to `OnboardingModule`. Passing score. |
| `AssessmentQuestion` | `assessments` | FK to `Assessment`, ordered. |
| `AssessmentAttempt` | `assessments` | Volume table, several thousand rows. Check constraint keeping score between 0 and 100. |
| `OnboardingTask` | `onboarding_tasks` | Non-learning tasks. `ManyToManyField` to `Department`. |
| `TaskAssignment` | `onboarding_tasks` | Two FKs to `User`, one for the assignee and one for the approver. Approval is a transactional multi-model write. |
| `Skill` | `skills` | `VectorField(dimensions=384)` for the embedding, with an `HnswIndex` using `opclasses=['vector_cosine_ops']`. |
| `UserSkill` | `skills` | Explicit through model for `User` to `Skill`. Unique constraint on the pair. This is the many-to-many whose read cost gets measured. |
| `ActivityEvent` | `activity` | Primary volume table, 100,000+ rows. `JSONField` for metadata. `occurred_at` is set once on creation, non-null, and effectively unique, which makes it the cursor pagination key. Three indexes, each added because a query plan asked for it, and each ending in `occurred_at` so the cursor can be sought rather than sorted to: `(user, -occurred_at)` for the user-scoped feed, `(-occurred_at)` for the unfiltered feed, and `(event_type, -occurred_at)` for the type-scoped feed. |

Every model gets `__str__`, `Meta.ordering`, `related_name` on every relationship, and a deliberate `on_delete` you can justify.

## Endpoints

| Endpoint | Purpose | Expected traffic | Optimization level | Query count |
|---|---|---|---|---|
| `ModuleListApi` | All onboarding modules, paginated | Low, viewed once per new hire during onboarding setup | `LimitOffsetPagination` through the `get_paginated_response` helper, default 10, capped at 50. The `COUNT` the paginator adds is the second query, and it is worth paying: without it the endpoint serializes the whole module catalogue on every call. No related fields touched, so no `select_related` | 2 (1 `COUNT`, 1 page) |
| `ModuleDetailApi` | One module by id | Low, one lookup per module viewed | Plain, no related fields touched | 1 |
| `MyDashboardApi` | Current user's assignments, pending tasks, completion percentage | High, every page load | Tight. `.values()` instead of model instances, module title and task title pulled in via `F()` lookups so no `select_related` needed, completion percentage computed in Python from the already-fetched rows rather than a third query. Cached in Redis per user, 5 minute TTL as a safety net, explicitly invalidated on task approval via `transaction.on_commit`. Invalidation on module completion is not wired yet since no endpoint changes `ModuleAssignment.status` today; add it there when that endpoint exists. `user_id` is a query param standing in for `request.user.id` until Phase 10 auth lands. Measured: cold cache 4.69ms (2 queries) versus warm cache 0.25ms (0 queries), roughly 19x. See `manage.py benchmark_dashboard_cache` | 2 on cache miss (measured), 0 on cache hit (measured) |
| `ActivityEventListApi` | Activity feed, cursor paginated | Moderate, a volume table (100,000+ rows) that gets paged deeply | Cursor pagination on `-occurred_at`, chosen over limit/offset because deep pages never pay an OFFSET scan, and chosen over `id` because every index on this table ends in `occurred_at`, so the planner can seek to the cursor instead of sorting to find it. Filters (`user_id`, `event_type`) validated by a `FilterSerializer`, filtering done in the selector. No related fields serialized, so no `select_related` needed. Cursor pagination issues no `COUNT`, which is the other half of why it stays at one query. Measured 99% deep into 100,004 seeded rows: PageNumberPagination (OFFSET) 85.07ms versus CursorPagination (WHERE seek) 3.94ms, roughly 22x. See `manage.py benchmark_pagination`, and `manage.py explain_queries` for the plans behind the three indexes | 1 |
| `UserDetailApi` | Full user object | Low, one lookup per profile viewed | `select_related("department", "manager")`, both touched by the serializer | 1 |
| `UserSkillsApi` | One user's skills, its own endpoint rather than a filter parameter | Low to moderate, viewed per profile | `select_related("skill")` on the `UserSkill` through model. Worth being precise: `User` has no `ManyToManyField` to `Skill`, so this is a reverse FK to `UserSkill` followed by a forward FK to `Skill`, and that second hop is the N+1. Measured on a user with 6 skills: no `select_related` 7 queries / 10.34ms, `select_related` 1 query / 1.23ms (8.4x), `prefetch_related` 2 queries / 1.96ms. The JOIN beats the prefetch because the hop being collapsed is a forward FK. See `manage.py benchmark_user_skills`. `LimitOffsetPagination` adds the `COUNT` | 2 (1 `COUNT`, 1 page), and flat as skills grow |
| `UserReportsApi` | Direct manager and direct reports only | Low, one lookup per profile viewed | `select_related("manager")` plus `prefetch_related("direct_reports")`, one query each since a JOIN can't collapse a reverse FK list into the parent row | 2 |
| `SkillSearchApi` | Vector similarity search over skill descriptions | Low, ad hoc searches | `CosineDistance` ordering against the HNSW index. Embedding the query text happens synchronously in the request, unlike `Skill` create's embedding, since a search response can't be returned before its own vector exists. Deliberately not paginated: the result set is already bounded by a validated `limit` capped at 50, and a similarity search wants the closest few, not a path to the last page. Honest caveat on the index: `EXPLAIN ANALYZE` shows a `Seq Scan`, not an HNSW scan, because there are only 20 seeded skills and the planner is right to ignore an index on a table that size. HNSW usage is therefore unverified at realistic volume, and should be re-checked once the skills table is larger | 1 |
| `TaskApprovalApi` | POST. Approves a task assignment and records an activity event in one transaction | Low, one call per approval | Scoped lookup (`assignee__manager_id`) inside the selector doubles as the authorization check, so an unauthorized manager gets 404 rather than a distinguishable permission error | 1 read (scoped fetch) + 2 writes (`TaskAssignment` update, `ActivityEvent` create), all inside one `transaction.atomic` |
| `DepartmentActivityReportApi` | Department-wide report | Low, occasional admin use | Deliberately unoptimized: one query per department for headcount, total assignments, completed assignments, and activity event count, rather than one annotated aggregate query. Acceptable for an occasional report, would need rework if run per-request. Also deliberately not paginated: the selector has already run every query by the time the view could slice its list, so an envelope would save nothing, and the row count is bounded by the number of departments. If departments ever numbered in the hundreds the fix is the aggregate query, not pagination | 1 + 4 × department count (33 measured against seed data, 8 departments) |

Authorization for each of these lives in the permissions table above, not here. When you add an endpoint, add a row to both tables in the same change.

## Celery tasks

| Task | Trigger | Notes |
|---|---|---|
| `generate_skill_embedding(skill_id)` | Service, on skill create or description change | The slow operation moved out of the request cycle. Enqueue with `transaction.on_commit`. |
| `score_assessment_attempt(attempt_id)` | Service, on attempt submit | Must be idempotent. Running it twice produces the same result. |
| `send_overdue_reminders()` | Beat | Retries with exponential backoff, since notification sends fail transiently. |
| `rollup_department_progress()` | Beat, nightly | Periodic aggregation. Candidate for a dedicated queue. |

Tasks are thin. A task fetches what it needs by ID and calls a service. Business logic lives in the service, not the task. Import the service inside the task function body to avoid circular imports, and import the task at module level with a `_task` suffix where a service triggers it.

A task runs outside the request cycle, so it has no `request.user` and no permission class. Any authorization a task's work depends on has already been decided by the service that enqueued it. Say so explicitly when you write a task, because "who was allowed to cause this" is not visible from inside the worker.

## Commands

```powershell
docker compose up
docker compose down
docker compose up --build
docker compose down -v   # also drops the db and model-cache volumes

docker compose exec web python manage.py migrate
docker compose exec web python manage.py makemigrations
docker compose exec web python manage.py makemigrations --check --dry-run   # must report no changes after any models/ edit
docker compose exec web python manage.py shell
docker compose exec web python manage.py seed_data --events 100000
docker compose exec web python manage.py test

# Performance measurement. All four want seeded data at volume, and
# explain_queries will warn you if the table is too small to plan meaningfully.
docker compose exec web python manage.py benchmark_pagination
docker compose exec web python manage.py benchmark_dashboard_cache
docker compose exec web python manage.py benchmark_user_skills
docker compose exec web python manage.py explain_queries

docker compose exec db psql -U postgres -d onboarding

docker compose logs -f celery-worker

docker compose exec web ruff check .
docker compose exec web ruff format .
```

## Style

- **No em-dashes anywhere.** Not in code comments, not in docstrings, not in documentation, not in generated seed data. Use commas, colons, or separate sentences.
- Type-annotate service and selector functions.
- Service and selector functions take keyword-only arguments unless they take zero or one argument.
- Service naming follows `<entity>_<action>`: `task_approve`, `skill_create`. Selector naming follows the same pattern: `module_list`, `user_dashboard_get`.
- Ruff for linting and formatting. Do not hand-format around it.

## How to work in this repo

- Prompts here are narrowly scoped on purpose, usually one checklist item at a time. Do not expand scope. If a prompt asks for one endpoint, do not also build three related ones.
- **Justify structure, not just code.** When you create, move, or split a file, say why it belongs there, and name the placement you rejected and what it would have cost. When you design anything with more than one reasonable shape, present the alternative before you commit to one. "Explain your file structure and why you built it this way and not another way" is a standing question in this repo, so answer it without being asked.
- **Do not default to the simplest thing that satisfies the prompt.** If a more production-realistic approach exists, name it and say what it costs in complexity, then recommend one. The goal is not the shortest path to a passing test.
- If a prompt is ambiguous, ask one question rather than guessing across several assumptions.
- If you are uncertain whether something is accurate for Django 6.0 or for this specific setup, say so and name what to check. A confident wrong answer costs more time here than an honest uncertain one.
- If a prompt would violate a convention in this file, say which convention and why before writing anything.
- Prefer pointing at the canonical documentation page over reproducing its content.
- When you touch the schema, the endpoint list, the permissions table, or the task list, update the corresponding table in this file in the same change.
- Do not fix an **OPEN** row in the permissions table opportunistically. Those are scheduled Phase 10 work and changing them out of order will break the tests that currently pin the pre-auth behaviour.
- **Delegate exploration, not comprehension.** For file discovery, locating a symbol, or answering "where is X," dispatch the built-in `Explore` subagent rather than walking the tree yourself. It is read only, runs on Haiku, and keeps its findings out of the main context window, which is the scarcer resource on a long session. Do not delegate a read whose exact contents the main session needs. That includes any file you are about to edit, any code being reviewed against the conventions in this file, and any symbol inventory that has to be exhaustive. A subagent returns a summary, and a summary is not reviewable.