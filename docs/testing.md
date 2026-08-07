# Testing

Phase 13's suite, built on top of the endpoint and Celery work from Phases
9 through 12. 188 tests as of this phase, organized by layer, mirroring the
architecture in CLAUDE.md rather than the sub-domain table alone: a selector's
tests live in `tests/selectors/`, a service's in `tests/services/`, a view's in
`tests/views/`, so finding the tests for a piece of code means opening the same
relative path one directory over.

Ruben's framing, quoted here because it sets the boundary of what this file
covers: important for a project this size, awkward around the multi-tenant
middleware patterns the real codebase uses, and their production suite is
large enough that nobody runs it locally anymore. So this project tests
properly, and middleware and multi-tenant testing stay out of scope entirely,
on purpose, not as an oversight.

## Layout

```
onboarding/tests/
├── __init__.py
├── factories.py            # factory_boy, one class per model
├── test_tasks.py            # direct task-function calls, policy pinning
├── test_celery_eager.py     # the one place CELERY_TASK_ALWAYS_EAGER runs for real
├── models/
│   ├── test_users.py         # get_direct_reports, __str__
│   ├── test_departments.py   # DepartmentProgressSnapshot's unique constraint
│   ├── test_modules.py       # ModuleAssignmentQuerySet.incomplete, is_overdue
│   ├── test_skills.py        # UserSkill's unique constraint
│   └── test_assessments.py   # AssessmentAttempt's two check constraints
├── selectors/
│   ├── test_users.py
│   ├── test_departments.py
│   ├── test_modules.py
│   ├── test_onboarding_tasks.py
│   ├── test_skills.py
│   ├── test_activity.py
│   └── test_dashboard.py
├── services/
│   ├── test_skills.py
│   ├── test_assessments.py
│   ├── test_departments.py
│   └── test_modules.py
└── views/
    ├── base.py               # EndpointFixtures, shared by every view test
    ├── test_invalid_input.py # one error envelope, reached from four endpoints
    ├── test_users.py
    ├── test_modules.py
    ├── test_departments.py
    ├── test_onboarding_tasks.py
    ├── test_skills.py
    ├── test_activity.py
    └── test_dashboard.py
```

Two absences are deliberate, not gaps. There is no `tests/models/test_onboarding_tasks.py`
or `tests/models/test_activity.py`, because `onboarding/models/onboarding_tasks.py`
and `onboarding/models/activity.py` have no method, property, or constraint beyond
a plain `__str__`. CLAUDE.md's own rule for the production layers, "create a module
only when that sub-domain has content," applies the same way to the tests that
exercise them: a file with nothing to assert is worse than no file. There is also
no `tests/selectors/test_assessments.py`, because `onboarding/selectors/` has no
`assessments.py` at all yet, per its own package docstring.

## Why the layer split, not just the sub-domain split

CLAUDE.md's architecture rule is that a selector never calls a service and a
service never duplicates a selector's scoping, and the point of testing each
layer directly rather than only through a view is that this is where that rule
actually gets checked. A view test proves an endpoint works. A selector test
proves the scoping decision itself is correct, independent of HTTP, independent
of whichever endpoint happens to call it today. `activity_event_list`'s three
scoping rules, self by default, one direct report for a manager, unrestricted
for staff, are pinned twice for exactly this reason: once in
`tests/views/test_activity.py` against the live endpoint, once in
`tests/selectors/test_activity.py` against the function directly. If a future
endpoint reuses that selector, its tests inherit a rule that was already proven
correct in isolation.

## Test data: factories vs. `EndpointFixtures`

Two different tools, kept deliberately separate rather than merged into one.

**`onboarding/tests/views/base.py`'s `EndpointFixtures`** is one fixed, shared
fixture set, built once per test class in `setUpTestData`. Every view test's
`assertNumQueries` assertion is only meaningful against a known database state,
and CLAUDE.md's endpoint table documents exact counts against this exact fixture
shape. Trimming a copy per file, or building it with factories that vary run to
run, would make a query-count regression indistinguishable from "this file just
seeded different rows." `EndpointFixtures` stays hand-rolled on purpose.

**`onboarding/tests/factories.py`** is for everything else: model tests, selector
tests, and service tests, where the point is arbitrary combinations and edge
cases (an overdue assignment, a duplicate skill name, a specific score), not a
fixed shape. `factory_boy`'s `DjangoModelFactory` classes there replace what
would otherwise be a `Model.objects.create(...)` call repeated with small
variations across a dozen test methods.

Two things worth knowing about the factories themselves:

- **`UserFactory.manager` defaults to `None`, never a `SubFactory`.** `User.manager`
  is self-referential, and a default `SubFactory(UserFactory)` would recurse
  infinitely trying to build a manager for the manager for the manager. A test
  that needs a manager passes one explicitly: `UserFactory(manager=some_user)`.
- **`SkillFactory.embedding` defaults to `[0.1] * 384`, never a zero vector.**
  Gotcha 16 in CLAUDE.md: cosine distance divides by the vector's norm, so a
  zero vector yields `NaN`, and pgvector's HNSW index cannot navigate a
  zero-vector row at all. A test that wants the pending, not-yet-embedded state
  overrides it explicitly: `SkillFactory(embedding=None)`.

## The test database and cache

The test database runs against the same containerized Postgres as development,
`manage.py test` builds and tears down a `test_<name>` database on it, which is
also why the pgvector extension migration (`0002_enable_pgvector`, `VectorExtension()`)
needs no special handling: Django runs every migration to build the test
database, so the extension is enabled there the same way it is anywhere else.

**The cache backend is swapped under test**, in `config/settings.py`:

```python
if TESTING:
    CACHES["default"] = {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
```

`TESTING` is `"test" in sys.argv`, the same flag that already gates the Debug
Toolbar. Without this override, tests would share the dev Redis instance, and a
`cache.clear()` in one test's `setUp` could clear a cache entry a concurrently
running `docker compose up` dev server just warmed, or vice versa.
`LocMemCache` is process-local and gone the moment the test process exits,
which satisfies Checklist 10's "separate Redis database or the local memory
cache" requirement either way. `MyDashboardApiTests` and every selector test
under `tests/selectors/test_dashboard.py` still call `cache.clear()` in
`setUp`, since `LocMemCache` persists for the life of the test process, not
per test.

## Celery: three different things "testing a task" means here

This project tests Celery tasks three distinct ways, and each one proves
something the other two do not.

**Calling the task function directly**, in `onboarding/tests/test_tasks.py`.
No broker, no worker, no eager mode, just `generate_skill_embedding(skill_id)`
as a plain Python call. This is the fastest and most direct way to test a
task's own logic, and it works because every task in this project is thin: it
fetches by ID and calls a service, so calling it directly exercises exactly
what a worker would run.

**Mocking the task at its enqueue site**, throughout `tests/services/` and
`tests/views/test_skills.py`. Every `assessment_attempt_create`,
`skill_create`, and `TaskApprovalApi` write path that enqueues something patches
the task (`patch("onboarding.services.skills.generate_skill_embedding_task")`,
for instance) and asserts on the call arguments inside
`self.captureOnCommitCallbacks(execute=True)`. This is the only way to test the
`transaction.on_commit` wiring in isolation: it proves the enqueue happens
after commit, with the right arguments, without needing the task's body to run
at all.

**Running the real, un-mocked chain with `CELERY_TASK_ALWAYS_EAGER`**, in
`onboarding/tests/test_celery_eager.py`, the one file where neither of the
above applies. `config/settings.py` sets this under `TESTING`:

```python
if TESTING:
    CELERY_TASK_ALWAYS_EAGER = True
    CELERY_TASK_EAGER_PROPAGATES = True
```

`apply_async` runs the task inline, in the calling process, the moment it is
called, rather than publishing to Redis. `AssessmentAttemptCreateEagerTests`
calls `assessment_attempt_create` inside `captureOnCommitCallbacks(execute=True)`
with nothing mocked, and asserts the attempt actually comes back scored,
proving the full path end to end: service enqueues, commit fires, the real
`apply_async` runs the real task, the real service scores the row, with no
worker process anywhere in the picture. `CELERY_TASK_EAGER_PROPAGATES` makes a
bug in the task fail the test that exercised it, rather than getting buried in
a stored `FAILURE` result nobody reads.

`score_assessment_attempt` is the task exercised here, not
`generate_skill_embedding`. The embedding task's body loads
`all-MiniLM-L6-v2`, and running that for real on every test invocation would
make the file slow and would coincidentally test the embedding provider
instead of the eager-mode wiring. Scoring is pure database logic with nothing
external to load, so it proves the same wiring at a fraction of the cost. If a
future test genuinely needs to prove the embedding task's real body runs
end to end, that is a deliberate, separate, slower test, not something to fold
in here.

## Query counts and the `TestCase` savepoint gotcha

`assertNumQueries` locks in the counts CLAUDE.md's endpoint table documents.
Two things to know before adding a new one:

- **A `transaction.atomic()` block inside `TestCase` costs two extra
  statements.** `TestCase` already wraps each test in a transaction, so a
  service's own `atomic()` becomes a nested `SAVEPOINT` / `RELEASE SAVEPOINT`
  pair, and `assertNumQueries` counts both. `SkillCreateApiTests` uses
  `CaptureQueriesContext` and filters those two statements out rather than
  pinning an inflated number; follow that pattern for any endpoint whose
  service wraps a write in `atomic()`.
- **`on_commit` callbacks never fire under plain `TestCase`.** It rolls back
  its transaction instead of committing, so anything enqueued via
  `transaction.on_commit` silently never runs, and a test that does not use
  `captureOnCommitCallbacks(execute=True)` around the call will pass for the
  wrong reason: it proves nothing was enqueued rather than proving the enqueue
  works.

## Commands

```powershell
docker compose exec web python manage.py test
docker compose exec web python manage.py test onboarding.tests.selectors
docker compose exec web python manage.py test onboarding.tests.models.test_modules
docker compose exec web python manage.py test onboarding.tests.selectors.test_activity.ActivityEventListTests.test_manager_can_view_direct_report_events

# Confirm nothing under models/ needs a migration, same check CLAUDE.md asks
# for after any models/ edit, worth rerunning after any test-data change too.
docker compose exec web python manage.py makemigrations --check --dry-run

docker compose exec web ruff check .
docker compose exec web ruff format .
```

## Things that bite

**`CELERY_TASK_ALWAYS_EAGER` being on does not mean a mocked test starts
running the real task.** `patch(...)` replaces the task object itself before
Celery's eager-mode logic is ever consulted, so every existing enqueue test
that mocks its task is unaffected by this setting. It only changes behavior
for code that calls the real, un-mocked `apply_async`, which as of this phase
is exactly one test file.

**A model test asserting a database constraint has to wrap the failing write
in `transaction.atomic()` and catch `IntegrityError` there,** the same pattern
`test_the_database_rejects_a_second_row_for_the_same_day` already uses in
`tests/services/test_departments.py`. An uncaught `IntegrityError` poisons the
outer `TestCase` transaction for the rest of that test method, so every
constraint test under `tests/models/` follows this shape.

**`ModuleAssignment.is_overdue` compares against `date.today()`.** There is no
time-freezing library in this project, so its tests use plain relative dates
(`date.today() - timedelta(days=1)`) rather than freezing the clock. That is
fine for a property with day-level granularity; it would not be for anything
sensitive to the exact moment.

**A partial `LocMemCache` state can leak between test classes that both touch
the dashboard cache**, since `LocMemCache` persists for the life of the test
process rather than being torn down per test. Every test class that reads or
writes it calls `cache.clear()` in `setUp`; a new dashboard- or
activity-adjacent test class needs the same line.

## Out of scope

- Middleware and multi-tenant testing, per Ruben's framing above. Nothing here
  simulates a second tenant or exercises custom middleware, because this
  project has neither.
- Load or concurrency testing of the idempotency guarantees. `assessment_attempt_score`'s
  conditional `UPDATE` and `rollup_department_progress`'s unique constraint are
  tested for correctness of the single-request case; a real concurrent race
  (two workers scoring the same attempt at once) is not simulated here, since
  Django's test transactions run single-threaded against one connection.
- Coverage measurement. No `coverage.py` in `requirements.txt` yet; the 188
  tests here were scoped against CLAUDE.md's endpoint, permissions, and task
  tables rather than against a percentage target.
