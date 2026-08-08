# Endpoints

Every endpoint this project exposes, what it is for, how often it is expected to be
called, and what it costs. Thirteen paths in total: eleven domain endpoints under
`/api/`, plus the two Simple JWT token views.

This is the human-facing reference. `CLAUDE.md` has a table of the same endpoints, but
it is organised around the optimization decision behind each one and does not carry a
single URL or HTTP method, because the model reads `onboarding/urls.py` for that. If the
two disagree, `onboarding/views/` and `onboarding/urls.py` are the truth and both tables
are stale.

## Conventions that apply to all of them

**Authentication.** `IsAuthenticated` is the project-wide default in
`REST_FRAMEWORK["DEFAULT_PERMISSION_CLASSES"]`. Every endpoint below requires a bearer
token, and no endpoint opts out. A request with no token is 401; a request whose token is
valid but whose caller fails an endpoint-specific check is 403 or 404, and which of the
two is a deliberate decision recorded per endpoint.

**One endpoint per data need.** There is no general-purpose endpoint driven by optional
filters. The full user object, that user's skills, and that user's reporting
relationships are three separate endpoints, because a caller that wants a name should not
pay for a skills join.

**One API class per operation.** `<Entity><Action>Api`, with `InputSerializer` and
`OutputSerializer` nested inside the class. A path answers 405 for a method no class
implements, which is why `POST /api/skills/` works and `GET /api/skills/` does not: there
is no `SkillListApi`, and inventing one to fill the gap in the URL table would be an
endpoint nothing has asked for.

**Three response shapes, and the difference is not cosmetic.** Two of the endpoints
return a bare JSON array rather than a pagination envelope, and a client has to know
which. See "Response envelopes" below.

**Errors are one shape.** `{"message": ..., "extra": {...}}`, produced by the single
handler in `api/exception_handlers.py`. On a validation failure the offending field names
are under `extra.fields`. A missing or malformed query parameter is 400 rather than a
quietly substituted default, on the grounds that answering a question the caller did not
ask is the harder of the two failures to debug.

## The endpoints

### Modules

| | |
|---|---|
| **`GET /api/modules/`** | `ModuleListApi`, URL name `module-list` |
| Purpose | The onboarding module catalogue: policy, security, benefits, culture |
| Expected volume | Low. Viewed once per new hire during onboarding setup |
| May call | Any authenticated user. The catalogue is the same for everyone, so nothing is scoped |
| Parameters | `limit` (default 10, max 50), `offset` |
| Returns | Pagination envelope of `{id, title, category, order}` |
| Queries | 2, one `COUNT` and one page |

`description` is deliberately absent from the list response and present in the detail
response. That is the whole reason the two endpoints are separate rather than one
endpoint with a `?verbose=` flag.

| | |
|---|---|
| **`GET /api/modules/<module_id>/`** | `ModuleDetailApi`, URL name `module-detail` |
| Purpose | One module, including its description |
| Expected volume | Low. One lookup per module opened |
| May call | Any authenticated user |
| Parameters | None |
| Returns | `{id, title, description, category, order}`, or 404 |
| Queries | 1 |

### Dashboard

| | |
|---|---|
| **`GET /api/dashboard/`** | `MyDashboardApi`, URL name `my-dashboard` |
| Purpose | The caller's own assigned modules, pending tasks, and completion percentage |
| Expected volume | **High. Hit on every page load**, and the reason this endpoint is tuned harder than any other |
| May call | Any authenticated user, for themselves only |
| Parameters | None, and that is the authorization mechanism |
| Returns | `{module_assignments: [{id, module_title, status, due_date, is_overdue}], pending_tasks: [{id, task_title, status}], completion_percentage}` |
| Queries | 2 on a cache miss, 0 on a hit |

There is no `user_id` parameter. The selector reads `request.user.id` directly, so there
is no way to ask for another employee's dashboard, and no permission class is needed to
enforce that. Cached in Redis per user under `onboarding:user_dashboard:{user_id}` with a
five minute TTL as a safety net, and invalidated explicitly on task approval through
`transaction.on_commit`. Measured at 4.69 ms cold against 0.25 ms warm, roughly 19x. See
`manage.py benchmark_dashboard_cache`.

Known gap, and it is a correctness gap rather than a performance one: nothing invalidates
this cache when a module assignment is completed, because no endpoint changes
`ModuleAssignment.status` yet. The invalidation call belongs in whichever endpoint
eventually does.

### Activity feed

| | |
|---|---|
| **`GET /api/activity-events/`** | `ActivityEventListApi`, URL name `activity-event-list` |
| Purpose | The activity feed, over the project's primary volume table |
| Expected volume | Moderate, but paged deeply. 100,000+ rows |
| May call | Any authenticated user. Self by default, a manager may pass one direct report's `user_id`, staff may pass any |
| Parameters | `user_id` (optional), `event_type` (optional, exact match not substring), `cursor` |
| Returns | Cursor envelope of `{id, user_id, event_type, metadata, occurred_at}` |
| Queries | 1 on the self and staff paths, 2 when a manager passes a report's id |

Cursor paginated on `-occurred_at`, not limit/offset, and the page size is fixed at 20
with no query parameter to change it. Measured 99% deep into 100,004 rows:
`PageNumberPagination` 85.07 ms against `CursorPagination` 3.94 ms, roughly 22x, because
a cursor page seeks to a `WHERE` position instead of counting past an `OFFSET`. All three
indexes on `ActivityEvent` end in `occurred_at` so the planner can seek rather than sort.
See `manage.py benchmark_pagination` and `manage.py explain_queries`.

A manager asking for an unrelated user's feed gets **403, not 404**. That is the opposite
call from `TaskApprovalApi` below, and it is deliberate: whether a given employee reports
to you is not sensitive, since `/api/users/<id>/reports/` already publishes the org chart.
The second query on the manager path is the `Exists` lookup that confirms the
relationship before the feed query runs.

### Users, the company directory

| | |
|---|---|
| **`GET /api/users/`** | `UserListApi`, URL name `user-list` |
| Purpose | The company directory, one flattened row per user |
| Expected volume | Low to moderate. Browsed occasionally, not hit per page load |
| May call | Any authenticated user, unscoped |
| Parameters | `username` (optional, **exact match**), `limit` (default 10, max 50), `offset` |
| Returns | Pagination envelope of `{id, username, name, email, is_staff, is_active, manager_name, department_name}` |
| Queries | 2, and flat as the directory grows |

`username` is an exact match rather than a search, because it is unique on `User`: a
caller filtering on it already knows the one row they want. There is no name search
endpoint. `name`, `manager_name` and `department_name` are annotations, not model fields,
built with `Concat`/`Trim`/`F()` so the whole page is one query with two `LEFT JOIN`s and
no `select_related`.

| | |
|---|---|
| **`GET /api/users/<user_id>/`** | `UserDetailApi`, URL name `user-detail` |
| Purpose | One user's full profile |
| Expected volume | Low. One lookup per profile viewed |
| May call | Any authenticated user, but **the response shape depends on who is asking** |
| Parameters | None |
| Returns | Self or staff: `{id, username, first_name, last_name, email, department, manager, is_active, date_joined}`. Anyone else: the same minus `email`, `is_active`, `date_joined` |
| Queries | 1 either way |

The branch is on which serializer runs, not on which query runs, so the trimmed response
costs exactly what the full one does. `department` and `manager` stay in both shapes,
because letting an employee see who reports to whom is the directory's entire purpose.

| | |
|---|---|
| **`GET /api/users/<user_id>/skills/`** | `UserSkillsApi`, URL name `user-skills` |
| Purpose | One user's skills and proficiency levels |
| Expected volume | Low to moderate. Viewed per profile |
| May call | Any authenticated user, unscoped |
| Parameters | `limit` (default 10, max 50), `offset` |
| Returns | Pagination envelope of `{skill_id, name, proficiency}` |
| Queries | 2, and flat as skills grow |

The N+1 here is subtle and worth knowing, since it is the many-to-many read the
performance rules warn about. `User` has no `ManyToManyField` to `Skill`: this is a
reverse FK to the `UserSkill` through model followed by a forward FK to `Skill`, and the
second hop is what multiplies. Measured on a user with six skills: 7 queries / 10.34 ms
untouched, 1 query / 1.23 ms with `select_related`, 2 queries / 1.96 ms with
`prefetch_related`. The JOIN wins because the hop being collapsed is a forward FK. See
`manage.py benchmark_user_skills`.

| | |
|---|---|
| **`GET /api/users/<user_id>/reports/`** | `UserReportsApi`, URL name `user-reports` |
| Purpose | Direct manager and direct reports, one level in each direction |
| Expected volume | Low. One lookup per profile viewed |
| May call | Any authenticated user, unscoped |
| Parameters | None |
| Returns | `{id, username, manager: {id, username}, direct_reports: [{id, username}]}` |
| Queries | 2 |

One level only, not the full subtree. Arbitrary-depth traversal needs a recursive CTE,
which the Django ORM does not express without raw SQL or a third-party package, and it is
tracked in the roadmap's deferred list rather than half-built here. Two queries rather
than one because a JOIN cannot collapse a reverse FK list into the parent row, so
`direct_reports` is a `prefetch_related`.

### Skills

| | |
|---|---|
| **`POST /api/skills/`** | `SkillCreateApi`, URL name `skill-create` |
| Purpose | Add a skill to the company-wide directory and hand its embedding to a worker |
| Expected volume | Low. Occasional additions |
| May call | **Staff only** (`IsStaff`). A non-staff caller gets 403, not 404 |
| Body | `{name, description}` |
| Returns | **201** with `{id, name, description, embedding_task_id}` |
| Queries | 2 in the request, plus 1 `SELECT` and 1 `UPDATE` later in the worker |

403 rather than 404 here is the opposite call from `TaskApprovalApi`, for the same reason
as the activity feed: the collection's existence is not a secret, and a client should be
able to tell the user the actual rule. Skills are company-wide reference data that
`/api/skills/search/` then returns to every employee, which is what makes "who may add
one" a caller-level question rather than a row-level one.

**The row comes back before it is searchable.** `embedding` is null at 201 and is filled
in by `generate_skill_embedding` on the `embeddings` queue, so a skill is invisible to
search until that task lands. 201 rather than 202 is deliberate: the resource exists and
is addressable the moment the call returns, and one field is pending. `embedding_task_id`
is the caller's handle for polling that, generated with `uuid4` in the service before the
commit rather than read off an `AsyncResult`, which does not exist until the `on_commit`
callback runs. The first query is bought on purpose: `full_clean()` costs a `SELECT` on
the unique `name` so a duplicate is a 400 naming the field instead of an `IntegrityError`
and a 500.

| | |
|---|---|
| **`GET /api/skills/search/`** | `SkillSearchApi`, URL name `skill-search` |
| Purpose | Find a skill from a vague description of a problem, by meaning rather than keyword |
| Expected volume | Low. Ad hoc searches |
| May call | Any authenticated user, unscoped |
| Parameters | `q` (**required**), `limit` (default 10, min 1, max 50) |
| Returns | A **bare JSON array** of `{id, name, description, distance}`, closest first |
| Queries | 1 |

Not paginated, and that is argued rather than skipped: the result set is already bounded
by a validated `limit`, and a similarity search wants the closest few, not a path to the
last page. Two mechanisms bounding one response would leave no obvious answer as to which
wins. `limit` above 50 is a 400 rather than a silent clamp, which is worth knowing because
DRF's own `LimitOffsetPagination` does the opposite on the paginated endpoints above.

`distance` is cosine distance, so lower is closer. Skills whose embedding is still null
are excluded rather than ranked, since there is no honest distance to report for a vector
that does not exist yet.

Honest caveat on the index: `EXPLAIN ANALYZE` currently shows a sequential scan, not an
HNSW index scan, because there are only 20 seeded skills and the planner is correct to
ignore an index on a table that size. HNSW usage is unverified at realistic volume.

### Task approvals

| | |
|---|---|
| **`POST /api/task-assignments/<task_assignment_id>/approve/`** | `TaskApprovalApi`, URL name `task-assignment-approve` |
| Purpose | A manager approves a completed non-learning onboarding task |
| Expected volume | Low. One call per approval |
| May call | The assignee's manager only (`IsAssigneeManager`, object-level) |
| Body | Empty |
| Returns | `{id, status, approved_at}` |
| Queries | 2 reads and 2 writes, the writes inside one `transaction.atomic` |

**404, not 403, for a task that is not yours.** The selector scopes its lookup by
`assignee__manager_id`, so an assignment belonging to another manager's report is
indistinguishable from one that does not exist. That is the point: unlike the activity
feed, the existence of a specific task assignment is information a caller outside the
reporting line should not get.

`POST` rather than `PATCH` because approval is a named action, not a field update. The
two reads are also deliberate: the view fetches through the scoping selector purely so
`check_object_permissions` has an object to check, and the service then re-fetches fresh
state inside its own transaction rather than trusting a read taken outside it. That is a
second read traded for an explicitly declared permission rule, since `has_object_permission`
does not fire automatically on a plain `APIView`.

Approving writes an `ActivityEvent` and invalidates the assignee's dashboard cache on
commit, both in the same transaction as the status change. Approving an assignment that is
already approved, or one that has not been completed, is a 400 carrying the service's
message.

### Reports

| | |
|---|---|
| **`GET /api/departments/activity-report/`** | `DepartmentActivityReportApi`, URL name `department-activity-report` |
| Purpose | Headcount, module completion percentage, and activity volume per department |
| Expected volume | Low. Occasional admin use |
| May call | **Staff only** (`IsStaff`) |
| Parameters | None |
| Returns | A **bare JSON array** of `{department_id, department_name, employee_count, completion_percentage, activity_event_count}` |
| Queries | 1 + 4 per department. **33 measured** against seed data with 8 departments |

**Deliberately unoptimized, and the only endpoint here that is.** It runs four queries per
department instead of one annotated aggregate, which is an easy trade for a report an
admin runs occasionally and would be indefensible for anything per-request. Not paginated
either: the selector has already run every query by the time the view could slice its
list, so an envelope would save nothing. If departments ever numbered in the hundreds, the
fix is the aggregate query, not pagination.

The nightly `rollup_department_progress` task calls this same selector, which is the
reason it is worth leaving alone: the live report and the stored history cannot drift into
two different definitions of completion percentage.

### Authentication

| | |
|---|---|
| **`POST /api/token/`** | `ThrottledTokenObtainPairView`, URL name `token-obtain` |
| **`POST /api/token/refresh/`** | `TokenRefreshView`, URL name `token-refresh` |
| Purpose | Trade credentials for an access and refresh token pair, and refresh the pair |
| Expected volume | Low. Once per login, then once per refresh cycle |
| May call | Anyone. These are the only unauthenticated endpoints |
| Body | `{username, password}` on obtain, `{refresh}` on refresh |
| Returns | `{access, refresh}` |
| Throttle | **5 per minute**, scoped |

Access tokens last 15 minutes, refresh tokens last one day. Refresh tokens rotate and the
replaced one is blacklisted, so a refresh response carries a new `refresh` value that the
client must store; reusing the old one afterwards fails. The throttle exists because
`UPDATE_LAST_LOGIN` writes a row on every successful obtain, which Simple JWT's own docs
flag as a denial-of-service vector without one.

These live in `config/urls.py` rather than `onboarding/urls.py`. They are stock Simple JWT
views, not `<Entity><Action>Api` classes owned by a sub-domain, so they sit beside the
admin registration instead of inside the domain app.

## Response envelopes

Three shapes, and a client needs to know which it is getting before it writes a loop.

**Limit/offset envelope**, on `/api/modules/`, `/api/users/`, and `/api/users/<id>/skills/`:

```json
{"limit": 10, "offset": 0, "count": 42, "next": "...", "previous": null, "results": [...]}
```

**Cursor envelope**, on `/api/activity-events/` only. No `count` and no `offset`, because
a cursor page has no notion of either, which is exactly why deep paging is cheap:

```json
{"next": "http://.../?cursor=cD0y", "previous": null, "results": [...]}
```

**Bare array**, on `/api/skills/search/` and `/api/departments/activity-report/`. Both are
documented exceptions to the paginate-everything rule, argued on their rows above.

Pagination is not automatic on a plain `APIView`, so all of the above goes through
`get_paginated_response` in `api/pagination.py` rather than a `pagination_class` attribute
that DRF would honour on a generic view.

## Error responses

Every error, whether DRF raised it or a service did, comes back in one shape from
`api/exception_handlers.py`.

| Status | When | Body |
|---|---|---|
| 400 | A serializer rejected the input | `{"message": "Validation error", "extra": {"fields": {"limit": ["..."]}}}` |
| 400 | A service raised `ApplicationError` | `{"message": "Task assignment is already approved.", "extra": {}}` |
| 401 | Missing, malformed, or expired token | `{"message": "...", "extra": {}}` |
| 403 | Caller failed a permission class, or the activity selector's scope check | `{"message": "...", "extra": {}}` |
| 404 | Row not found, or found but out of the caller's scope | `{"message": "Not found.", "extra": {}}` |
| 405 | Method not implemented on that path, for example `GET /api/skills/` | `{"message": "...", "extra": {}}` |
| 429 | Token endpoint throttle | `{"message": "...", "extra": {}}` |

`ApplicationError` is the one case DRF's own handler does not recognise, since it is not a
DRF exception, so it is translated to 400 explicitly in the same place rather than by
scattering `Response(status=400)` through the services.

`InvalidInputTests` in `onboarding/tests/views/test_invalid_input.py` pins this envelope
across four different endpoints, so the documented behaviour and the actual behaviour
cannot drift apart quietly.

## What is not here

- **No OpenAPI schema.** drf-spectacular introspects `serializer_class` and `queryset` on
  the view, and a plain `APIView` with nested serializers offers it almost nothing, so it
  would mean one `@extend_schema` decorator per endpoint. Deferred in the roadmap, on the
  grounds that it teaches nothing about Django and costs real time.
- **No `SkillListApi`, no `AssessmentAttemptCreateApi`, no module completion endpoint.**
  The `assessments` sub-domain owns models and services but no endpoints yet;
  `assessment_attempt_create` is reached from tests and the shell.
- **No write endpoints on modules, users, or departments.** Those rows are seeded and
  edited through the admin.
- **No filtering library.** `django-filter` is deferred pending a decision on whether
  RuroTech uses it. If it returns, it returns as a `FilterSet` instantiated inside the
  selector, not as a `filter_backends` entry on the view, because a filter backend does
  not apply to a plain `APIView` anyway.
