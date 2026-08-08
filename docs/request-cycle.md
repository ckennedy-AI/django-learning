# The Django request cycle, traced through this codebase

One real request, followed from the socket to the JSON, naming which layer owns each
decision. The point is not the internals of any one function. It is being able to take a
reported bug ("a manager is seeing a 403 on a report's feed") and know, before opening
anything, which of ten places could have produced it.

## The short version

Django hands an HTTP request through a middleware chain, matches its path against a
URLconf, and calls the view that path names. DRF wraps that view in more layers of its
own.

For `GET /api/activity-events/?user_id=12`:

1. **WSGI and middleware.** `config.wsgi` builds an `HttpRequest`. Seven middleware run
   top to bottom from `MIDDLEWARE`, each able to short-circuit and return early. On the
   way back out they run bottom to top, which is why response headers are added in
   reverse order from request checks.
2. **URL resolution.** `ROOT_URLCONF` is `config.urls`. `api/` includes
   `onboarding.urls`, whose `activity_event_patterns` matches `activity-events/` and
   names the view `ActivityEventListApi`. Any captured path converter, such as
   `<int:user_id>` on other endpoints, arrives as a keyword argument.
3. **DRF's `dispatch`.** `APIView.dispatch` replaces Django's `HttpRequest` with DRF's
   `Request`, then runs `initial()`: content negotiation, **authentication**,
   **permissions**, throttles. Authentication is lazy. Nothing runs until something
   touches `request.user`, which `initial()` does deliberately so a bad token fails here
   rather than halfway down a service.
4. **Authentication.** `JWTAuthentication` reads the `Authorization: Bearer` header,
   verifies the signature against `SIMPLE_JWT["SIGNING_KEY"]`, and loads the user named
   by the token's `user_id` claim. **That load is a database query**, and it happens
   before any application code runs.
5. **Permissions.** `IsAuthenticated`, the project-wide default, answers "may this caller
   invoke this endpoint at all". It does not answer "which rows", and conflating those
   two is the mistake this project is built to avoid.
6. **The view.** Three jobs only: validate input, call down, shape the response.
   `FilterSerializer` validates the query parameters and `is_valid(raise_exception=True)`
   turns a bad one into a 400 rather than a silent default.
7. **The selector.** Reads live in `selectors/`, writes in `services/`, and a selector
   never calls a service. `activity_event_list` decides the row scope from who is asking:
   self by default, one direct report for a manager (costing one extra `Exists` query),
   anything for staff, and a 403 otherwise. **It returns a queryset, not rows.** No SQL
   has run yet.
8. **The ORM.** Querysets are lazy. The `SELECT` is emitted at the moment something
   iterates, which here is the paginator slicing the queryset, not the selector building
   it. This is why a query count is a property of the whole request rather than of the
   selector.
9. **Pagination.** DRF does not paginate a plain `APIView` automatically, so
   `get_paginated_response` in `api/pagination.py` does it explicitly. Cursor pagination
   adds `ORDER BY occurred_at DESC LIMIT 21` and, past page one, a `WHERE occurred_at <`
   seek instead of an `OFFSET`.
10. **The `OutputSerializer`.** Turns model instances into primitives. No ORM access
    here, so a field the selector did not fetch would trigger a query from inside
    serialization, which is the classic N+1.
11. **Response and render.** A DRF `Response` carries unrendered data until the renderer
    turns it into JSON, then the middleware chain runs back up and WSGI writes the bytes.

On the error path, nothing above builds an error response itself. An exception propagates
to the single handler in `api/exception_handlers.py`, which normalises every failure,
DRF-native or not, to `{"message": ..., "extra": {...}}`.

The rest of this document is the same trace with the actual code, the actual SQL, and the
places where the abstraction leaks.

---

## The request being traced

```http
GET /api/activity-events/?user_id=12&event_type=task_approved HTTP/1.1
Host: localhost:8000
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

The caller is user 7, a manager. User 12 is one of their direct reports.

`ActivityEventListApi` is chosen over the simpler endpoints on purpose: it is the only one
that exercises authentication, a permission class, input validation, a caller-dependent
row scope, cursor pagination, and a 403 raised from inside a selector, all in one request.
`ModuleDetailApi` would fit in a paragraph and teach a third as much.

## 1. WSGI and the middleware chain

`config/wsgi.py` exposes the application object Gunicorn or `runserver` calls. Django
builds an `HttpRequest` from the WSGI environ and hands it to the middleware chain from
`config/settings.py`, in order:

| Middleware | Does what, here |
|---|---|
| `SecurityMiddleware` | Security headers on the way out. No redirect, since `SECURE_SSL_REDIRECT` is unset |
| `SessionMiddleware` | Loads a session from a cookie. This API does not use sessions, but the admin does, so it stays |
| `CommonMiddleware` | `APPEND_SLASH`. A request to `/api/activity-events` without the trailing slash is redirected to the version with it |
| `CsrfViewMiddleware` | Does nothing here: `APIView.as_view()` is wrapped in `csrf_exempt`, and a bearer token is not a cookie, so there is no CSRF surface to protect |
| `AuthenticationMiddleware` | Sets `request.user` lazily from the **session**. See the trap below |
| `MessageMiddleware` | Admin flash messages. Unused by the API |
| `XFrameOptionsMiddleware` | `X-Frame-Options` on the way out |

Middleware is a stack, not a queue: each one runs its request half top to bottom, then the
response halves run bottom to top. Anything that returns a response early skips every
layer below it, including the view.

**The trap worth knowing.** `AuthenticationMiddleware` sets `request.user` on the *Django*
`HttpRequest`, from the session. DRF then wraps that request and defines its own
`request.user` property backed by `DEFAULT_AUTHENTICATION_CLASSES`. Inside a view, the
Django one is unreachable. That is why a session login in the admin does not authenticate
an API call, and why deleting `AuthenticationMiddleware` would break the admin while
leaving every endpoint here working.

## 2. URL resolution

`ROOT_URLCONF = "config.urls"`. Django strips the leading slash and matches the remaining
path against `urlpatterns` in order:

```python
# config/urls.py
path("admin/", admin.site.urls),
path("api/token/", ThrottledTokenObtainPairView.as_view(), name="token-obtain"),
path("api/token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
path("api/", include("onboarding.urls")),
```

`api/` matches by prefix, so `include` re-enters with `activity-events/` as the remaining
path and resolves it inside `onboarding/urls.py`:

```python
# onboarding/urls.py
activity_event_patterns = [
    path("activity-events/", ActivityEventListApi.as_view(), name="activity-event-list"),
]
```

Two things this step does not do. It does not look at the HTTP method, so `POST` to this
path resolves to the same view and fails later with 405 from `dispatch`. And it does not
look at the query string at all: `?user_id=12` is not part of the path, so it plays no
part in resolution and arrives as data on the request.

Every pattern is named, and nothing in this project references a URL by hardcoded string.
`reverse("activity-event-list")` is what the tests call, which means a path can be
restructured without touching a test.

## 3. `as_view`, `dispatch`, and `initial`

`ActivityEventListApi.as_view()` returned a plain function at import time. Calling it
instantiates the class per request, so no state survives between requests, and calls
`dispatch`.

`dispatch` does three things before the handler:

**`initialize_request`** wraps the `HttpRequest` in a DRF `Request`. This is where
`request.data` and `request.query_params` come from, and where the authenticator list is
attached.

**`initial`** runs the cross-cutting checks:

```python
self.perform_content_negotiation(request)   # picks the JSON renderer
self.determine_version(request, ...)        # no versioning configured
self.perform_authentication(request)        # touches request.user, forcing lazy auth
self.check_permissions(request)             # has_permission on every class
self.check_throttles(request)               # no throttle_scope here, so a no-op
```

`perform_authentication` is one line, `request.user`, and that is the whole point: it
forces the lazy authentication to resolve *here*, where a failure is a clean 401, rather
than at some unpredictable later moment.

**Handler lookup** maps the lowercased HTTP method to a method on the class. `get` exists,
so it is called with the request and any captured path kwargs. If it did not exist,
`http_method_not_allowed` would produce the 405.

**Gotcha 15 lives in this step.** `dispatch` calls `check_permissions`, so
`has_permission` runs on every request automatically. It never calls
`check_object_permissions`, because DRF only does that from `GenericAPIView.get_object()`,
which this project does not use. On a plain `APIView`, object-level permissions run only
where a view calls `self.check_object_permissions(request, obj)` by hand, which
`TaskApprovalApi` does and this endpoint has no need to.

## 4. Authentication

`JWTAuthentication` from `DEFAULT_AUTHENTICATION_CLASSES`:

1. Reads the `Authorization` header and requires the `Bearer` prefix. No header at all
   means no authenticator succeeds, `request.user` becomes `AnonymousUser`, and the
   permission class rejects it a moment later.
2. Validates the token: signature against `SIMPLE_JWT["SIGNING_KEY"]`, which is
   `JWT_SIGNING_KEY` from the environment and deliberately not `SECRET_KEY`, plus the
   `exp` claim against a 15 minute lifetime. A failure raises `InvalidToken`, which is a
   DRF `AuthenticationFailed` subclass, and becomes 401.
3. Loads the user named by the `user_id` claim and checks `is_active`.

```sql
SELECT id, password, last_login, is_superuser, username, first_name, last_name,
       email, is_staff, is_active, date_joined, department_id, manager_id
  FROM onboarding_user
 WHERE id = 7
 LIMIT 21;
```

The `LIMIT 21` is not a typo and has nothing to do with pagination. Simple JWT calls
`User.objects.get(...)`, and Django's `get()` fetches up to `MAX_GET_RESULTS`, which is 21,
so it can raise `MultipleObjectsReturned` with a useful count instead of silently taking
the first row. Every `get()` in this codebase compiles to `LIMIT 21`.

**This query is real and the documented query counts do not include it.** The view tests
use `force_authenticate`, which sets `request.user` directly and skips the authenticator
entirely, so `assertNumQueries(1)` on this endpoint means one query *after* authentication.
A production request pays two. That is a deliberate testing convenience rather than a
measurement error, but it is worth knowing before comparing a documented count against a
Debug Toolbar reading.

The token is stateless: nothing is looked up in a session table, and there is no
server-side record of an issued access token. Only *refresh* tokens have a database
presence, through the blacklist app, and only after rotation.

## 5. Permission classes

`ActivityEventListApi` declares no `permission_classes`, so it inherits
`IsAuthenticated` from settings. `check_permissions` loops the classes and calls
`has_permission(request, view)` on each; any `False` raises `PermissionDenied` and ends
the request as 403, or 401 if no authenticator was even attempted.

The important part is what this class does **not** do. It answers "may user 7 call this
endpoint", nothing more. It does not know that `?user_id=12` was passed, and it must not:
deciding whether user 12 reports to user 7 needs a database query, and a permission class
that runs queries to find rows has quietly become a selector.

That split is the reason `SkillCreateApi` and `DepartmentActivityReportApi` can be fully
described by `permission_classes = [IsAuthenticated, IsStaff]`, while this endpoint's real
rule lives in its selector.

Note that declaring `permission_classes` on a view **replaces** the default list rather
than extending it, which is why both endpoints above list `IsAuthenticated` explicitly
next to `IsStaff`. Omitting it would silently drop the authentication requirement.

## 6. The view's own work

```python
def get(self, request):
    filters_serializer = self.FilterSerializer(data=request.query_params)
    filters_serializer.is_valid(raise_exception=True)

    events = activity_event_list(
        requesting_user=request.user, filters=filters_serializer.validated_data
    )

    return get_paginated_response(...)
```

Three lines, three jobs: validate input, call down, shape the response. No ORM access, no
business logic, no scoping decision. Everything the view knows about authorization is that
it passes `request.user` downward and lets the layer that can answer the question answer
it.

`FilterSerializer` declares `user_id` as an `IntegerField` and `event_type` as a
`CharField`, both optional. `?user_id=abc` fails validation and becomes a 400 naming the
field. It does **not** become an unfiltered feed, which is the substantive choice here: a
default silently substituted for a malformed parameter returns a plausible answer to a
question nobody asked, and that is the harder failure to notice.

`validated_data` is also a type conversion boundary. `request.query_params` values are all
strings; `validated_data["user_id"]` is an `int`. The selector's `target_user_id ==
requesting_user.id` comparison depends on that, and would silently be `False` for every
caller if the raw string were passed through.

## 7. The selector, where row scoping lives

```python
# onboarding/selectors/activity.py
if target_user_id is None or target_user_id == requesting_user.id:
    scoped_user_id = requesting_user.id
elif requesting_user.is_staff:
    scoped_user_id = target_user_id
elif User.objects.filter(id=target_user_id, manager_id=requesting_user.id).exists():
    scoped_user_id = target_user_id
else:
    raise PermissionDenied(...)

queryset = ActivityEvent.objects.filter(user_id=scoped_user_id)

if event_type := filters.get("event_type"):
    queryset = queryset.filter(event_type=event_type)

return queryset
```

Our manager reaches the third branch, which costs the one extra query that separates this
path's count of 2 from the self and staff paths' count of 1:

```sql
SELECT 1 AS "a" FROM onboarding_user
 WHERE (id = 12 AND manager_id = 7)
 LIMIT 1;
```

`.exists()` compiles to `SELECT 1 ... LIMIT 1` rather than fetching the row, because the
question is a boolean and nothing downstream needs the columns.

Two design points are visible in these fifteen lines.

**The 403 is raised here, in a read.** A selector may reject a caller; what it may not do
is *write*. That is the layering rule, and it is directional: services call selectors,
never the reverse.

**403, not 404, and that is the opposite of `TaskApprovalApi`.** Returning 404 hides
whether the row exists. Here there is nothing to hide, because
`/api/users/<id>/reports/` already publishes the org chart, so an accurate error a client
can display beats a misleading one. On `TaskApprovalApi` the existence of a specific task
assignment *is* information a stranger should not have, so its selector scopes the lookup
and lets `get_object_or_404` produce a 404 that does not distinguish "not yours" from
"does not exist".

**Nothing has hit the database for the feed itself yet.** The last three lines build a
queryset object. `filter()` returns a new queryset every time and executes nothing.

## 8. The ORM, and where the SQL actually happens

A queryset is lazy. It carries a query it has not run, and it runs it the first time
something needs rows: iteration, `len()`, `list()`, `bool()`, slicing with a step, or
pickling. Slicing without a step stays lazy and adds `LIMIT`/`OFFSET` to the pending
query, which is exactly what the paginator relies on.

So the selector returns, the view calls the pagination helper, and only inside
`paginate_queryset` does anything reach Postgres:

```sql
SELECT id, user_id, event_type, metadata, occurred_at
  FROM onboarding_activityevent
 WHERE (user_id = 12 AND event_type = 'task_approved')
 ORDER BY occurred_at DESC
 LIMIT 21;
```

`LIMIT 21` for a page size of 20: DRF fetches one extra row to learn whether a next page
exists without paying a `COUNT`.

The `ORDER BY` is served by `activity_user_occurred_idx` on `(user, -occurred_at)`, one of
three indexes on this table that each end in `occurred_at`. Ending in the cursor column is
what lets the planner seek to a position instead of sorting the matches to find it, and
each of the three exists because an `EXPLAIN ANALYZE` plan asked for it rather than because
indexing felt prudent. `manage.py explain_queries` prints the plans.

On page two the shape changes in the way that matters:

```sql
 WHERE (user_id = 12 AND event_type = 'task_approved'
        AND occurred_at < '2026-08-01 09:14:22.518+00')
 ORDER BY occurred_at DESC
 LIMIT 21;
```

A `WHERE` seek, not `OFFSET 20000`. That is the whole argument for cursor pagination on
this table: 85.07 ms against 3.94 ms, measured 99% deep into 100,004 rows by
`manage.py benchmark_pagination`.

## 9. Pagination, which is not automatic here

Gotcha 4: DRF applies pagination on generic views and viewsets, and this project uses
neither. `api/pagination.py` does it explicitly:

```python
paginator = pagination_class()
page = paginator.paginate_queryset(queryset, request, view=view)
if page is not None:
    serializer = serializer_class(page, many=True)
    return paginator.get_paginated_response(serializer.data)
```

`paginate_queryset` is where the queryset is ordered, sliced, and executed, and where the
opaque `?cursor=` value is decoded. `page` is a list of `ActivityEvent` instances, so
everything after this point is in memory.

The cursor envelope has no `count` and no `offset`, unlike the limit/offset envelope the
module, user, and skills endpoints return. That is not a formatting difference: a
`COUNT(*)` over this table is the second query those endpoints pay and the one this
endpoint deliberately does not.

## 10. The `OutputSerializer`

```python
class OutputSerializer(serializers.ModelSerializer):
    class Meta:
        model = ActivityEvent
        fields = ("id", "user_id", "event_type", "metadata", "occurred_at")
```

Instances to primitives, and nothing else. Serializers hold no business logic and touch no
ORM, which is a performance rule as much as an architectural one: **a serializer field
that reaches a relation the selector did not fetch triggers one query per row, from a
layer nobody thinks to look at when reading a query count.** Serializing `user.username`
instead of `user_id` here would turn one query into twenty-one.

`user_id` rather than a nested user object is the same decision the endpoint table records
as "return only the fields the endpoint needs". A feed row does not need the employee's
department.

Serializers are nested inside the API class and not shared between endpoints. A shared
serializer that grows a field for one caller changes the payload for every other caller
silently, and there is no test that fails when a response gains a key nobody asked for.

## 11. Response, rendering, and back out

`Response` is DRF's, not Django's, and it holds **unrendered** data. The renderer chosen
during content negotiation runs when `dispatch` finalizes the response, converting the
`OrderedDict` to JSON bytes and setting `Content-Type: application/json`.

That deferral is why `response.data` in a test is a Python structure rather than a byte
string, and it is also why gotcha 16 fails the way it does: a `NaN` distance survives
every layer above and only explodes at the renderer, because JSON has no `NaN`.

Then the middleware chain runs back up, bottom to top, and WSGI writes the bytes.

## The error path

No layer above builds an error response. Each raises, and exactly one place translates.

Take the same request from a manager who is **not** user 12's manager. Everything through
step 6 is identical, then:

1. The selector raises Django's `PermissionDenied`.
2. It propagates up through the view, which catches nothing.
3. `dispatch` catches it in `handle_exception` and calls the handler named by
   `REST_FRAMEWORK["EXCEPTION_HANDLER"]`.
4. `api/exception_handlers.py` converts Django's `PermissionDenied` to DRF's, hands it to
   DRF's own handler for the status code, then rewrites the body:

```json
{
  "message": "You may only view your own activity feed or a direct report's.",
  "extra": {}
}
```

Three exception types are translated to their DRF equivalents on the way in, because DRF's
handler only understands its own: Django's `ValidationError`, `Http404`, and
`PermissionDenied`. A fourth, `ApplicationError` from `core/exceptions.py`, is not a DRF
exception and has no DRF equivalent, so it is handled where DRF's handler returns `None`
and becomes a 400.

Anything that reaches the handler and is none of these returns `None` all the way out,
which Django turns into a 500. That is correct: an unrecognised exception is a bug, and a
bug should not be laundered into a tidy 4xx.

A validation failure from step 6 takes the same route and is the one case with a populated
`extra`:

```json
{
  "message": "Validation error",
  "extra": {"fields": {"user_id": ["A valid integer is required."]}}
}
```

`InvalidInputTests` pins this envelope across four endpoints, so the documentation and the
behaviour cannot drift apart quietly.

## What the write path adds

`POST /api/task-assignments/42/approve/` is identical through step 5, then differs in ways
worth naming.

**An object-level permission check, run by hand.** The view fetches through the scoping
selector and calls `self.check_object_permissions(request, task_assignment)` explicitly,
because `dispatch` never does it on a plain `APIView`. `IsAssigneeManager` then checks
`obj.assignee.manager_id`, which costs nothing extra only because the selector
`select_related("assignee")`.

**A service instead of a selector.** Writes and business logic live in `services/`. A
service may call selectors, other services, models, and enqueue tasks. It may not be
called by a selector.

**A transaction.** `task_assignment_approve` wraps its work in `transaction.atomic`, so
the status change and the `ActivityEvent` either both land or neither does. It also
re-fetches inside the transaction rather than trusting the view's read, which was taken
outside it.

**Errors as exceptions, not responses.** An already-approved assignment raises
`ApplicationError`, which becomes a 400 in the same single handler. No service in this
project constructs a `Response`.

**Work that outlives the response.** `transaction.on_commit` schedules the dashboard cache
invalidation for after the commit. On `SkillCreateApi` the same mechanism enqueues a Celery
task, and the ordering is load-bearing: a worker is a separate process with its own
connection and would read a row that has not committed yet. Under `TestCase` these
callbacks never fire at all, because the test's transaction is rolled back, which is what
`captureOnCommitCallbacks(execute=True)` exists for.

**One more gotcha in the counting.** `transaction.atomic` inside a `TestCase` becomes a
`SAVEPOINT` / `RELEASE SAVEPOINT` pair, and `assertNumQueries` counts both. A service
wrapped in `atomic` therefore reports two more statements under test than it issues in
production.

## Reading this backwards, from a bug report

The layer split earns its keep when something breaks. "A manager gets a 403 on their
report's feed" has exactly five candidate causes, and they are checkable in order:

| Symptom | Layer | Where to look |
|---|---|---|
| 401, not 403 | Authentication | Expired access token, or `JWT_SIGNING_KEY` changed under a live token |
| 403 on every endpoint | Permission class | `DEFAULT_PERMISSION_CLASSES`, or a view whose `permission_classes` dropped `IsAuthenticated` |
| 400 naming `user_id` | View | `FilterSerializer`, the parameter is malformed and never reached the selector |
| 403 naming the feed | Selector | `activity_event_list`, so `target.manager_id != requesting_user.id` in the database. The org chart is wrong, not the code |
| 200 with the wrong rows | Selector | The scope branch, not the permission class. The permission class cannot see `user_id` at all |

Each row names one file. That is the entire return on the layering rules: a bug is
traceable in one direction, and no two layers can both be responsible for the same
decision.
