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
| `users` | `User` | `UserListApi`, `UserDetailApi`, `UserSkillsApi`, `UserReportsApi` |
| `departments` | `Department`, `DepartmentProgressSnapshot` | `DepartmentActivityReportApi` |
| `modules` | `OnboardingModule`, `ModuleAssignment` | `ModuleListApi`, `ModuleDetailApi` |
| `assessments` | `Assessment`, `AssessmentQuestion`, `AssessmentAttempt` | none yet |
| `onboarding_tasks` | `OnboardingTask`, `TaskAssignment` | `TaskApprovalApi` |
| `skills` | `Skill`, `UserSkill` | `SkillSearchApi`, `SkillCreateApi` |
| `activity` | `ActivityEvent` | `ActivityEventListApi` |
| `dashboard` | none, it is a cross-domain read | `MyDashboardApi` |

Rules for placement:

- **An API class goes in the module named for the `<Entity>` in `<Entity><Action>Api`.** `UserSkillsApi` is a user endpoint, so it lives in `views/users.py`, even though its selector reads `UserSkill`. This is a mechanical rule on purpose, so placement is never a judgement call.
- **A selector or service goes in the module named for the sub-domain of the endpoint it serves.** The same mechanical rule as the API classes, and for the same reason: every layer of one endpoint shares a filename. `user_skills_list` lives in `selectors/users.py` because it serves `UserSkillsApi`, even though it reads `UserSkill`. Chosen deliberately over "the entity it primarily reads", which would have put that selector in `selectors/skills.py` while its view sat in `views/users.py`, splitting one endpoint across two sub-domains and defeating the point of the layout.
- Two tie-breakers, in order, for a function no endpoint reaches directly. **First, it goes with the entity that owns the outcome:** `task_assignment_approve` writes an `ActivityEvent` but its outcome is an approved `TaskAssignment`, so it lives in `services/onboarding_tasks.py`. **Second, where that is still ambiguous, it goes with its caller in the same layer:** `user_dashboard_cache_invalidate` lives in `selectors/dashboard.py` beside `user_dashboard_get` because the two share a cache key, and a key helper separated from one of its callers is how invalidation silently stops matching.
- **Create a module only when that sub-domain has content in that layer.** An empty `services/activity.py` is worse than no file. `assessments` has no endpoints yet, so it has no `views/assessments.py`.
- `onboarding_tasks` is named that way, not `tasks`, to keep it unambiguous against `onboarding/tasks.py`, which holds Celery tasks and nothing else.

### Package import conventions

- Each `__init__.py` re-exports the public names from its submodules, so import paths outside the package do not change: `from onboarding.selectors import module_list`, not `from onboarding.selectors.modules import module_list`.
- `models/__init__.py` re-exporting every model is not optional, it is how Django discovers them. See caveat 14.
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
- **Object-level checks are not automatic on plain `APIView`.** See caveat 15.
- A write endpoint states, in the same explanation as the code, who may write and what the response is on a scope violation.

### Permissions table

`IsAuthenticated` is the real DRF default as of Phase 10 (`DEFAULT_PERMISSION_CLASSES`), so every row below is enforced, not aspirational. Nothing here is a to-do.

The **State** column says what enforces the row, not whether it is finished:

- **Default only** means the project-wide `IsAuthenticated` is the entire rule. No permission class on the view, no `requesting_user` argument in the selector. The row is complete; it just has nothing endpoint-specific in it.
- **Endpoint-specific** means something beyond that default: the view declares its own `permission_classes`, the selector scopes its rows by the caller, or the view narrows the request to the caller before the selector ever sees it. That extra work is described in the two columns to the left.

| Endpoint | May call | Row scope | State |
|---|---|---|---|
| `ModuleListApi` | `IsAuthenticated` | Unscoped. The module catalogue is the same for every employee | Default only |
| `ModuleDetailApi` | `IsAuthenticated` | Unscoped | Default only |
| `MyDashboardApi` | `IsAuthenticated` | `request.user` only, always. Reads `request.user.id` directly, no query parameter, so there is no way to ask for anyone else's dashboard. Cache key unchanged (`onboarding:user_dashboard:{user_id}`), only its source changed | Endpoint-specific |
| `ActivityEventListApi` | `IsAuthenticated` | Self by default (no `user_id` param). A manager may pass `user_id` for exactly one direct report, checked via an `Exists` lookup in the selector (`target.manager_id == request.user.id`). Staff may pass any `user_id` unrestricted. A manager requesting an unrelated user's feed gets 403: unlike `TaskApprovalApi`, org-chart membership is not sensitive, `UserReportsApi` already exposes it | Endpoint-specific |
| `UserListApi` | `IsAuthenticated` | Unscoped read of the directory | Default only |
| `UserDetailApi` | `IsAuthenticated` | Unscoped fetch, but the response is scoped: self or staff get the full object, any other caller gets a trimmed serializer dropping `email`, `is_active`, `date_joined` | Endpoint-specific |
| `UserSkillsApi` | `IsAuthenticated` | Unscoped read | Default only |
| `UserReportsApi` | `IsAuthenticated` | Unscoped read | Default only |
| `SkillSearchApi` | `IsAuthenticated` | Unscoped, minus skills whose embedding is still null. That exclusion is a correctness filter, not an authorization scope: an un-embedded row has no distance to rank by | Default only |
| `SkillCreateApi` | `IsAuthenticated`, plus `IsStaff` (`onboarding/permissions.py`) | No rows to scope, it is a create. A skill is company-wide reference data that `SkillSearchApi` then returns to every employee, so who may add one is a caller-level question. A non-staff caller gets 403, not 404: the collection's existence is not sensitive and the client should be able to report the rule accurately, which is the opposite call from `TaskApprovalApi` | Endpoint-specific |
| `TaskApprovalApi` | `IsAuthenticated`, plus `IsAssigneeManager` (object-level, `onboarding/permissions.py`) | `assignee__manager_id == request.user.id`, applied in the selector, which still returns 404 for a non-report task before the permission class ever runs. The permission class exists so the endpoint declares this rule the same way every other row here does, and so a future change to the selector's scoping does not silently drop enforcement | Endpoint-specific |
| `DepartmentActivityReportApi` | `IsAuthenticated`, plus `IsStaff` (`onboarding/permissions.py`) | Unscoped once the caller is staff | Endpoint-specific |

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
- **Moving a model between modules inside the same app is not a schema change and must not generate a migration.** Django identifies a model by app label and class name, not by module path. If `makemigrations --check --dry-run` reports changes after a pure file move, something is wrong. See caveat 14.

## Known caveats

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
15. **`check_object_permissions` is not called automatically on a plain `APIView`.** DRF calls `check_permissions` in `initial()`, so `has_permission` runs on every request, but `has_object_permission` only runs where `GenericAPIView.get_object()` would have called it. On these API classes it has to be invoked explicitly after fetching the object. This is the same shape of problem as caveat 4: the convenience lives in the generics this project does not use.
16. **A zero vector breaks pgvector search in two different ways, and neither one errors.** Cosine distance divides by the vector's norm, so a zero vector on either side yields `NaN`. Worse, an HNSW graph cannot be navigated through a zero-vector row, so an index scan silently returns *nothing* for a small `LIMIT` while a `LIMIT` above `hnsw.ef_search` (default 40) falls back to a sequential scan and returns the row with a `NaN` distance, which DRF's JSON renderer then refuses to encode. `[0.0] * 384` is the obvious thing to write in a fixture and it made `SkillSearchApiTests` assert its query count against an empty result set for two phases. Fixtures and seed data use a non-zero vector.
17. **`config/__init__.py` must import the Celery app.** `@shared_task` registers against whichever app is current, so the app has to exist by the time `onboarding/tasks.py` is imported. Without that import the `web` process still imports the task symbol and still calls `.apply_async()` on it, so the failure surfaces as a broker or worker problem rather than a missing import.
18. **`autodiscover_tasks()` is what finds `tasks.py`.** Without it the worker starts cleanly, banners an empty task list, and rejects every message with `NotRegistered`. Read the banner after a restart: the registered task list is printed there.
19. **`CELERY_TASK_SERIALIZER = "json"` is what enforces caveat 3.** On the default serializer a model instance pickles happily and arrives at the worker as a stale snapshot. Pinned to JSON, the enqueue fails immediately in the process that has the useful stack trace.
20. **`PENDING` does not mean queued.** It means no state is stored under that task id, which also covers an id that was never a task. `STARTED` only exists because `CELERY_TASK_TRACK_STARTED` is on.
21. **The worker does not reload on code changes,** and Celery's own reloader is documented as unsuitable for anything but experimentation. `docker compose restart celery-worker`. Forgetting means `web` runs new code while the worker runs old code.
22. **Each prefork worker child loads its own copy of the embedding model.** Worker `--concurrency` is a memory decision here, not a throughput dial, and the `hf-cache` volume must be mounted into whichever worker consumes the embedding task or it downloads its own copy of `all-MiniLM-L6-v2`. Since the Phase 12 queue split that is `celery-worker-embeddings`, not `celery-worker`: the latter deliberately does **not** mount the volume, so a future routing mistake that sends an embedding to the wrong queue produces a slow first run rather than a silently working one. The variable pointing at that cache is `HF_HOME`, set in the Dockerfile. There is deliberately no `HF_TOKEN`: `all-MiniLM-L6-v2` is public and ungated, and `huggingface_hub` reads `HF_TOKEN` from the environment whether or not this project asks it to, so setting a placeholder sends a bearer token on a request that would have succeeded anonymously.
23. **`transaction.atomic` inside `TestCase` becomes a `SAVEPOINT` / `RELEASE SAVEPOINT` pair,** and `assertNumQueries` counts both. A service wrapped in `atomic` therefore reports two more statements under test than it issues in production. Filter them out with `CaptureQueriesContext` rather than pinning the inflated number, as `SkillCreateApiTests` does.
24. **`get_or_create` and `update_or_create` are check-then-write, so neither is idempotent on its own.** Both issue a `SELECT` and then an `INSERT`, and two callers can both pass the select. What makes `update_or_create` safe in `department_progress_rollup` is the unique constraint underneath it: the loser's `INSERT` raises `IntegrityError`, which Django catches and turns into a re-fetch. Remove the constraint and the same code silently writes duplicates. Where the thing that must happen once is a state transition rather than a row, there is nothing for a constraint to be unique about, and the answer is a conditional `UPDATE ... WHERE` whose affected row count is the gate, as `assessment_attempt_score` does.
25. **A queue with no worker consuming it accumulates messages silently.** Routing a task in `CELERY_TASK_ROUTES` without a worker started on `-Q <queue>` produces no error anywhere: the enqueue succeeds, the message sits in Redis, and the only symptom is a task that never runs. Both worker services in `docker-compose.yml` name their queue explicitly for this reason.
26. **A route is keyed by task name, which is the module path plus function name.** Renaming a task function or moving `onboarding/tasks.py` silently orphans its route and sends it to `default`, where a worker that never loads the embedding model would run it. `TaskExecutionPolicyTests` pins the name.
27. **`soft_time_limit` and `time_limit` are not the same mechanism.** The soft limit raises `SoftTimeLimitExceeded` inside the task, so it can clean up; the hard limit is a `SIGKILL` to the worker child, so no exception is raised and no `finally` runs. Setting them equal makes the soft limit useless. The project defaults are 60 and 90, and `generate_skill_embedding` raises both because a cold worker child loads the model first.
28. **Beat does not backfill a missed run, and that is the less dangerous direction.** A firing that was due while beat was down is skipped, with no catch-up and no record. The case worth guarding is the reverse: beat up and workers down means messages accumulate and then all run at once, which is what `expires` in each `CELERY_BEAT_SCHEDULE` entry prevents.
29. **Only one beat process may run.** Two schedulers on the same schedule publish every task twice, and the idempotency work in the services is the only thing standing between that and duplicate effects. `PersistentScheduler`'s shelve file also takes an exclusive lock, so reading it requires stopping beat first.
30. **Flower shows nothing useful until task events are on.** `CELERY_WORKER_SEND_TASK_EVENTS` and `CELERY_TASK_SEND_SENT_EVENT` are both off by default, and without them Flower can only report the queue. Its `/api/` endpoints separately return 401 unless `--unauthenticated_api` is passed, which is Flower's own default rather than a misconfiguration here.
31. **A task's return value must be JSON-serializable, including its dates.** `CELERY_RESULT_SERIALIZER = "json"` rejects a `date` as readily as it rejects a model instance, which is why the two scheduled services return `.isoformat()` strings rather than date objects.
32. **`annotate()` with an aggregate does not preserve `Meta.ordering` usefully.** It feeds the ordering column into the `GROUP BY`, and the resulting row order is not the one the model declares. Any selector whose consumer cares about order, especially a batch task that has to resume in a stable sequence, needs an explicit `order_by()`. `module_assignment_overdue_user_list` orders by `id` for exactly that reason, which one of its tests caught.
33. **`TESTING` (`"test" in sys.argv`) gates more than the Debug Toolbar as of Phase 13.** It also swaps `CACHES` to `LocMemCache` and turns on `CELERY_TASK_ALWAYS_EAGER` plus `CELERY_TASK_EAGER_PROPAGATES`, all in `config/settings.py`. The cache swap keeps a test run from sharing cache state with a concurrently running `docker compose up` dev server. The eager setting only affects tests that call the real, un-mocked `apply_async`, which as of this phase is exactly one file (`onboarding/tests/test_celery_eager.py`): every other enqueue test patches its task, and a patched task is replaced before Celery's eager-mode logic is ever consulted, so turning this on did not change what those tests were asserting.

## File layout

Everything tracked in the repo, so an absence here means the file does not exist rather than that it was left out.

```
manage.py
Dockerfile
docker-compose.yml
requirements.txt
pyproject.toml           # Ruff lint and format configuration
.env.example             # every environment variable, with why each one exists
README.md                # setup and orientation for a human, not for you
CLAUDE.md                # this file
project-checklist.md     # the requirements document
django-learning-roadmap.md
django-styleguide.md     # HackSoft, the architectural spec
docs/
  docker.md              # container command reference and volume caveats
  celery.md              # worker topology, Redis db split, failure modes.
                         # Its task table is the human-facing version of the
                         # Celery task table below, so Checklist 12's task
                         # documentation needed no new file.
  testing.md             # layer-by-layer test layout, factories vs fixtures,
                         # the three ways a Celery task gets tested
  endpoints.md           # Added Phase 14. The human-facing endpoint reference:
                         # method, path, URL name, parameters, response shape,
                         # expected volume, query count. Not a duplicate of the
                         # endpoint table below, which carries no URL and no HTTP
                         # method because this file's reader has onboarding/urls.py.
  ci.md                  # Added Phase 14. The operational half of CI: branch
                         # protection and the staging and production
                         # environments, both repository settings rather than
                         # files, plus how to reproduce a CI failure locally.
  request-cycle.md       # Added Phase 14. One request traced end to end through
                         # this codebase, with the real SQL. Roadmap Phase 14's
                         # deliverable, and the reference for the layering rules
                         # above read in execution order rather than by layer.
.claude/
  skills/                # comprehension-check, start-phase
.github/
  workflows/
    ci.yml               # lint, test, build, deploy, deploy-production. Added
                         # Phase 14. Postgres and Redis are service containers,
                         # not Compose services, so DATABASE_URL points at
                         # localhost rather than db: job steps run on the
                         # runner, not inside a container
config/
  __init__.py            # imports the Celery app, see caveat 17
  settings.py
  urls.py                # admin, JWT token views, includes onboarding.urls
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
                           # assessments.py, departments.py and modules.py were
                           # added in Phase 12, each because a Celery task needs
                           # a service to call. None of the three is reached by
                           # an endpoint, so each is placed by the tie-breakers.
  tests/
    __init__.py
    factories.py            # factory_boy, one class per model, added Phase 13
    models/                 # methods, properties, constraints. Added Phase 13.
                           # No test_onboarding_tasks.py or test_activity.py:
                           # those two model modules have nothing non-trivial
                           # to test, per the "only when that sub-domain has
                           # content" rule below.
    selectors/              # every selector, called directly rather than
                           # through a view. Added Phase 13. Mirrors
                           # selectors/ exactly, so no test_assessments.py
                           # either, since selectors/assessments.py does not
                           # exist yet.
    views/
    services/              # views/ and services/ appeared in Phases 9 and 11
                           # respectively, per the "only when that sub-domain
                           # has content" rule.
    test_tasks.py           # flat, mirroring flat onboarding/tasks.py: one module
                           # under test, so a tests/tasks/ package would hold one
                           # file forever
    test_celery_eager.py    # the one file where CELERY_TASK_ALWAYS_EAGER runs a
                           # real, un-mocked task. Flat for the same reason as
                           # test_tasks.py: one cross-cutting concern, not a
                           # sub-domain split. Added Phase 13.
  admin.py                 # SkillAdmin routes creates through skill_create
  apps.py
  permissions.py           # DRF permission classes, created in Phase 10
  tasks.py                 # Celery tasks only, created in Phase 11. Four tasks
                           # as of Phase 12, plus their retry and time limit
                           # policy. Queue routing and the schedule are in
                           # settings, not here.
  urls.py
  embeddings.py            # embed_texts provider function
  migrations/              # 0002 enables pgvector and must precede 0003
  management/commands/     # seed_data, three benchmarks, explain_queries,
                           # inspect_task_result
```

Tests are organised by layer first and sub-domain second, following HackSoft: `tests/selectors/test_modules.py` holds the tests for `selectors/modules.py`. The file naming convention is `test_<module_name>.py` and the test case naming convention is `class <ThingUnderTest>Tests(TestCase)`.

The layer directories mirror the layers they test, including whether the layer is a package. `onboarding/tasks.py` is a flat file, so its tests are `tests/test_tasks.py` at the top of the package rather than `tests/tasks/test_tasks.py`: a directory for a single module would hold one file until `tasks.py` itself gets promoted, and the layout should not claim a sub-domain split that the layer does not have.

`docs/testing.md` holds the operational side: the full layout, when to reach for `factories.py` versus `EndpointFixtures`, the three distinct ways a Celery task gets tested in this project, and the query-count and `on_commit` caveats worth meeting once.

Two files in `tests/views/` are deliberate exceptions to that naming, and both are exceptions because what they hold is not one module's tests:

- `base.py` holds `EndpointFixtures`, the single fixture set every view test inherits. Every per-endpoint test asserts an exact query count from the endpoint table above, and those counts are only comparable against a known database state. Sharing one fixture set rather than trimming a copy per file is what keeps a count change meaning "an N+1 appeared" instead of possibly meaning "this file seeds different rows". It is not named `test_*.py`, so the runner does not collect it as a module.
- `test_invalid_input.py` holds `InvalidInputTests`, which reaches four different endpoints on purpose. What it pins is the single error envelope in `api/exception_handlers.py`, one policy rather than one endpoint's behaviour, so splitting it per endpoint would scatter one decision across four files. It inherits no fixtures, because every case in it is rejected before a query runs.

**Deviation from HackSoft on naming:** the styleguide names the API layer `apis.py`. This repo names it `views/` instead, to match the repository owner's company convention. This is deliberate, not drift. Every other HackSoft convention still applies: plain `APIView` classes, `<Entity><Action>Api` naming, `InputSerializer` and `OutputSerializer` nested inside each class. Only the name differs.

## Schema

Thirteen models. This section is the intent; `onboarding/models/` is the truth. If they disagree, read the models package and tell the repository owner this section is stale.

| Model | Module | Notes |
|---|---|---|
| `User` | `users` | Custom, subclasses `AbstractUser`. Self-referential FK `manager`. FK `department`. `AUTH_USER_MODEL` must be set before the first migration. |
| `Department` | `departments` | Org units. |
| `DepartmentProgressSnapshot` | `departments` | Added Phase 12. One row per department per day, written by `rollup_department_progress` and read by nothing yet, which is normal for a rollup. `UniqueConstraint` on `(department, captured_on)` is load-bearing rather than hygienic: it is what makes the nightly task idempotent. `captured_on` is the date described, not the moment written, so a rerun lands on the right row. Chosen over caching the report payload, which would forget, and a cache is not a history. |
| `OnboardingModule` | `modules` | Policy, security, benefits, culture content. Category choices, explicit ordering. |
| `ModuleAssignment` | `modules` | FK to `User` and `OnboardingModule`. Status choices, `due_date`, `completed_at`. Property deriving overdue state. |
| `Assessment` | `assessments` | `OneToOneField` to `OnboardingModule`. Passing score. |
| `AssessmentQuestion` | `assessments` | FK to `Assessment`, ordered. |
| `AssessmentAttempt` | `assessments` | Volume table, several thousand rows. Check constraint keeping score between 0 and 100. Nullable `passed` and `scored_at` as of Phase 12: the row is written by the request and scored by a worker, so "submitted but not scored" is a real state, and `False` would wrongly claim the attempt was scored and failed. `scored_at` is also the concurrency gate for `assessment_attempt_score`, so nothing else may write it, and a second check constraint keeps the two columns set or unset together. That is a constraint rather than a `clean()` check because the writer is a worker calling `.update()`, which never runs `full_clean`. |
| `OnboardingTask` | `onboarding_tasks` | Non-learning tasks. `ManyToManyField` to `Department`. |
| `TaskAssignment` | `onboarding_tasks` | Two FKs to `User`, one for the assignee and one for the approver. Approval is a transactional multi-model write. |
| `Skill` | `skills` | `VectorField(dimensions=384)` for the embedding, with an `HnswIndex` using `opclasses=['vector_cosine_ops']`. Nullable as of Phase 11: the vector is written by a Celery task, not by the request that creates the row, so there is a real window where the skill exists without it. `skill_search` excludes those rows. |
| `UserSkill` | `skills` | Explicit through model for `User` to `Skill`. Unique constraint on the pair. This is the many-to-many whose read cost gets measured. |
| `ActivityEvent` | `activity` | Primary volume table, 100,000+ rows. `JSONField` for metadata. `occurred_at` is set once on creation, non-null, and effectively unique, which makes it the cursor pagination key. Three indexes, each added because a query plan asked for it, and each ending in `occurred_at` so the cursor can be sought rather than sorted to: `(user, -occurred_at)` for the user-scoped feed, `(-occurred_at)` for the unfiltered feed, and `(event_type, -occurred_at)` for the type-scoped feed. |

Every model gets `__str__`, `Meta.ordering`, `related_name` on every relationship, and a deliberate `on_delete` you can justify.

## Endpoints

| Endpoint | Purpose | Expected traffic | Optimization level | Query count |
|---|---|---|---|---|
| `ModuleListApi` | All onboarding modules, paginated | Low, viewed once per new hire during onboarding setup | `LimitOffsetPagination` through the `get_paginated_response` helper, default 10, capped at 50. The `COUNT` the paginator adds is the second query, and it is worth paying: without it the endpoint serializes the whole module catalogue on every call. No related fields touched, so no `select_related` | 2 (1 `COUNT`, 1 page) |
| `ModuleDetailApi` | One module by id | Low, one lookup per module viewed | Plain, no related fields touched | 1 |
| `MyDashboardApi` | Current user's assignments, pending tasks, completion percentage | High, every page load | Tight. `.values()` instead of model instances, module title and task title pulled in via `F()` lookups so no `select_related` needed, completion percentage computed in Python from the already-fetched rows rather than a third query. Cached in Redis per user, 5 minute TTL as a safety net, explicitly invalidated on task approval via `transaction.on_commit`. Invalidation on module completion is not wired yet since no endpoint changes `ModuleAssignment.status` today; add it there when that endpoint exists. Reads `request.user.id` directly as of Phase 10, no query parameter, same cache key format. Measured: cold cache 4.69ms (2 queries) versus warm cache 0.25ms (0 queries), roughly 19x. See `manage.py benchmark_dashboard_cache` | 2 on cache miss (measured), 0 on cache hit (measured) |
| `ActivityEventListApi` | Activity feed, cursor paginated | Moderate, a volume table (100,000+ rows) that gets paged deeply | Cursor pagination on `-occurred_at`, chosen over limit/offset because deep pages never pay an OFFSET scan, and chosen over `id` because every index on this table ends in `occurred_at`, so the planner can seek to the cursor instead of sorting to find it. Filters (`user_id`, `event_type`) validated by a `FilterSerializer`, scoping and filtering done in the selector. As of Phase 10, `user_id` absent or equal to the caller's own id stays on the self path (no extra query); a manager passing a direct report's id costs one additional `Exists` query to confirm the relationship before the feed query runs; staff skip that check. No related fields serialized, so no `select_related` needed. Cursor pagination issues no `COUNT`, which is the other half of why the self and staff paths stay at one query. Measured 99% deep into 100,004 seeded rows: PageNumberPagination (OFFSET) 85.07ms versus CursorPagination (WHERE seek) 3.94ms, roughly 22x. See `manage.py benchmark_pagination`, and `manage.py explain_queries` for the plans behind the three indexes | 1 (self or staff path), 2 (manager viewing one direct report, the extra query is the `Exists` relationship check) |
| `UserListApi` | The company directory, one flattened row per user. One optional filter, `username`, validated by a nested `FilterSerializer` and applied in the selector as an exact match rather than a search, since `username` is unique | Low to moderate, browsed occasionally rather than hit per page load | `.values()` with `Concat`/`Trim`/`F()` annotations rather than model instances plus `select_related`, since nothing downstream ever touches a related object, only flat columns. Both `department` and `manager` are nullable, so Django emits a `LEFT OUTER JOIN` for each, matching the two `LEFT JOIN`s in the source query, in one query. `LimitOffsetPagination` adds the `COUNT` | 2 (1 `COUNT`, 1 page), flat as the directory grows |
| `UserDetailApi` | Full user object, trimmed for a non-self, non-staff caller | Low, one lookup per profile viewed | `select_related("department", "manager")`, both touched by whichever serializer is chosen. As of Phase 10, the view picks between two `OutputSerializer`s after the fetch: the full one (`email`, `is_active`, `date_joined` included) for `request.user.id == user.id` or `request.user.is_staff`, a trimmed one otherwise. The branch is on which serializer runs, not on the query, so this stays one query either way | 1 |
| `UserSkillsApi` | One user's skills, its own endpoint rather than a filter parameter | Low to moderate, viewed per profile | `select_related("skill")` on the `UserSkill` through model. Worth being precise: `User` has no `ManyToManyField` to `Skill`, so this is a reverse FK to `UserSkill` followed by a forward FK to `Skill`, and that second hop is the N+1. Measured on a user with 6 skills: no `select_related` 7 queries / 10.34ms, `select_related` 1 query / 1.23ms (8.4x), `prefetch_related` 2 queries / 1.96ms. The JOIN beats the prefetch because the hop being collapsed is a forward FK. See `manage.py benchmark_user_skills`. `LimitOffsetPagination` adds the `COUNT` | 2 (1 `COUNT`, 1 page), and flat as skills grow |
| `UserReportsApi` | Direct manager and direct reports only | Low, one lookup per profile viewed | `select_related("manager")` plus `prefetch_related("direct_reports")`, one query each since a JOIN can't collapse a reverse FK list into the parent row | 2 |
| `SkillCreateApi` | POST. Creates a skill and hands its embedding to a Celery task, returning 201 immediately | Low, occasional additions to the directory | Two queries, and the first one is bought deliberately: `full_clean()` in the service costs a `SELECT` on the unique `name` so a duplicate is a 400 naming the field rather than an `IntegrityError` and a 500. 201 rather than 202, because the resource exists and is addressable the moment the call returns, with one field pending. The response carries `embedding_task_id`, generated in the service with `uuid4` before the commit rather than read off the `AsyncResult`, since that object only exists inside the `on_commit` callback, which runs after the service has returned. No related fields, no serialization of the 384-float vector | 2 (1 `SELECT` for the unique check, 1 `INSERT`), plus 1 `SELECT` and 1 `UPDATE` in the worker, outside the request |
| `SkillSearchApi` | Vector similarity search over skill descriptions | Low, ad hoc searches | `CosineDistance` ordering against the HNSW index, with `exclude(embedding__isnull=True)` as of Phase 11 so a skill whose task has not run yet is left out rather than ranked by a distance that does not exist. Embedding the query text happens synchronously in the request, unlike `SkillCreateApi`'s embedding, since a search response can't be returned before its own query vector exists. Deliberately not paginated: the result set is already bounded by a validated `limit` capped at 50, and a similarity search wants the closest few, not a path to the last page. Honest caveat on the index: `EXPLAIN ANALYZE` shows a `Seq Scan`, not an HNSW scan, because there are only 20 seeded skills and the planner is right to ignore an index on a table that size. HNSW usage is therefore unverified at realistic volume, and should be re-checked once the skills table is larger | 1 |
| `TaskApprovalApi` | POST, empty body. Approves a task assignment and records an activity event in one transaction | Low, one call per approval | Scoped lookup (`assignee__manager_id`) inside the selector doubles as the authorization check, so an unauthorized manager gets 404 rather than a distinguishable permission error. As of Phase 10, the view also fetches the object via that same selector before the service runs, purely to give `check_object_permissions` (`IsAssigneeManager`) something to check, then the service re-fetches fresh state inside its own `transaction.atomic` rather than trusting a read taken outside the transaction. That is a second read added deliberately, traded for an explicit, declared permission check per caveat 15 rather than relying solely on the selector's `WHERE` clause | 2 reads (view's permission-check fetch, service's transactional re-fetch) + 2 writes (`TaskAssignment` update, `ActivityEvent` create), the writes inside one `transaction.atomic` |
| `DepartmentActivityReportApi` | Department-wide report | Low, occasional admin use | Deliberately unoptimized: one query per department for headcount, total assignments, completed assignments, and activity event count, rather than one annotated aggregate query. Acceptable for an occasional report, would need rework if run per-request. Also deliberately not paginated: the selector has already run every query by the time the view could slice its list, so an envelope would save nothing, and the row count is bounded by the number of departments. If departments ever numbered in the hundreds the fix is the aggregate query, not pagination. `IsStaff` (`onboarding/permissions.py`) as of Phase 10, purely a permission-class decision, the selector's read stays unscoped | 1 + 4 × department count (33 measured against seed data, 8 departments) |
| `token-obtain` / `token-refresh` | POST. Stock `TokenObtainPairView` (subclassed only to add `throttle_scope = "token_obtain"`) and `TokenRefreshView` from `rest_framework_simplejwt.views` | Low, once per login/refresh cycle | Not part of the onboarding domain's endpoint surface (no `<Entity><Action>Api`, no `InputSerializer`/`OutputSerializer`), so it lives in `config/urls.py` beside the admin registration rather than in `onboarding/urls.py`. Throttled at `5/min` via `ScopedRateThrottle`, since `UPDATE_LAST_LOGIN` writes to the database on every successful call | 1 write (`last_login` update) on obtain, plus blacklist bookkeeping on refresh (`ROTATE_REFRESH_TOKENS` + `BLACKLIST_AFTER_ROTATION`) |

Authorization for each of these lives in the permissions table above, not here. When you add an endpoint, add a row to both tables in the same change.

## Celery tasks

| Task | Trigger | Queue | Retries | Time limits | Notes |
|---|---|---|---|---|---|
| `generate_skill_embedding(skill_id)` | `skill_create`, on skill create only | `embeddings` | None | 120 soft / 150 hard | **Built, Phase 11.** The slow operation moved out of the request cycle. Enqueued with `transaction.on_commit` via `apply_async(args=[skill.id], task_id=...)`, where the task id is pre-generated so the response can name it. Calls `skill_embedding_set`, returns `{"skill_id": ..., "dimensions": 384}` into the result backend. Idempotent by construction, since it recomputes from `description` and overwrites. A description change does **not** re-embed: there is no update endpoint and the admin's change path is a documented gap, not a wired trigger. **Routed to its own queue in Phase 12**, and it is the only routed task: its worker child is the only one that holds a sentence-transformers model in RAM, which makes its concurrency a memory decision the other tasks should not share. Its time limits are raised above the project default because a cold worker child loads the model before it encodes anything |
| `score_assessment_attempt(attempt_id)` | `assessment_attempt_create`, on attempt submit | `default` | None | 60 / 90 | **Built, Phase 12.** Calls `assessment_attempt_score`, which is **idempotent by compare-and-swap**: `UPDATE ... WHERE scored_at IS NULL` makes the test and the write one statement, and the affected row count decides whether this run owns the transition and may write the `ActivityEvent`. A second delivery updates zero rows and returns `{"scored": False}` with the verdict re-read from the row. Chosen over a unique constraint because what must happen once is a state transition on an existing row, and a constraint has nothing to be unique about. No retries: a missing attempt is a bug, not a transient outage. Its trigger is a service with no endpoint yet, since `assessments` owns none |
| `send_overdue_reminders()` | Beat, 13:00 UTC daily | `default` | `autoretry_for=(OSError,)`, `retry_backoff` to 600s, jitter, `max_retries=5` | 60 / 90 | **Built, Phase 12.** Calls `overdue_reminders_send`, which emails one message per user with overdue modules, not one per assignment. `smtplib.SMTPException` subclasses `OSError`, so one entry covers every way a mail server is unreachable, and nothing else is retried. Retry safety comes from the service being **resumable**, not just re-runnable: each reminder is logged as an `ActivityEvent` right after its send and the selector excludes anyone logged within a 20 hour window, so a batch that dies partway through resumes instead of re-sending. Deliberately not wrapped in `transaction.atomic`, which is the documented exception to the atomic-writes rule and the reason the resume works. At-least-once, not exactly-once |
| `rollup_department_progress()` | Beat, 02:30 UTC daily | `default` | None | 60 / 90 | **Built, Phase 12.** Calls `department_progress_rollup`, which writes one `DepartmentProgressSnapshot` per department per date. **Idempotent by unique constraint**: `update_or_create` is check-then-write and racy on its own, and `unique_department_snapshot_per_day` is what turns a lost race into a caught `IntegrityError` and one row. Reuses `department_activity_report_list`, the selector behind `DepartmentActivityReportApi`, so the nightly history and the live report cannot define completion percentage differently. Inherits that selector's 1 + 4 × department count queries, which is an easy trade at 02:30. `expires` on the beat entry matters more than a retry would |

Execution policy lives in three places on purpose. Retries and time limits are decorator arguments in `onboarding/tasks.py`, because they are properties of running that particular task. Queue routing is central in `CELERY_TASK_ROUTES`, because the map of queues should be readable in one place. The schedule is central in `CELERY_BEAT_SCHEDULE` for the same reason. All three are pinned by `TaskExecutionPolicyTests` in `onboarding/tests/test_tasks.py`, since a route that no longer matches a task name and a soft limit deleted in a refactor both change nothing about how the code reads.

Tasks are thin. A task fetches what it needs by ID and calls a service. Business logic lives in the service, not the task. Import the service inside the task function body to avoid circular imports, and import the task at module level with a `_task` suffix where a service triggers it.

`docs/celery.md` holds the operational side: topology, the Redis database number split, the commands, and the failure modes worth meeting once.

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

# Celery. Two workers, one per queue, plus beat and Flower. Nothing here reloads
# on code changes, so restart after touching onboarding/tasks.py, a service a
# task calls, or the beat schedule. See docs/celery.md.
docker compose up -d celery-worker celery-worker-embeddings celery-beat flower
docker compose logs -f celery-worker
docker compose logs -f celery-worker-embeddings
docker compose logs -f celery-beat
docker compose restart celery-worker celery-worker-embeddings celery-beat
docker compose exec web python manage.py inspect_task_result   # needs a live worker
docker compose exec celery-worker celery -A config inspect registered
docker compose exec celery-worker celery -A config inspect active_queues

# Flower, at http://localhost:5555. The UI is unauthenticated, so local only.
# Its /api/ endpoints return 401 by default in Flower 2.x, which is deliberate.

# Run a beat-scheduled task now instead of waiting for its crontab.
docker compose exec web python manage.py shell -c "from onboarding.tasks import send_overdue_reminders; print(send_overdue_reminders.delay().get(timeout=120))"

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
- Do not change an endpoint's authorization opportunistically. Every row in the permissions table is enforced and pinned by a test. Tightening a scope that a prompt did not ask about will break those tests, and the fix belongs in the phase that owns it.