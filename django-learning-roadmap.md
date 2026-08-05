# Django Learning Roadmap

**Project:** Employee Onboarding Platform (backend only)
**Purpose:** Build foundational Django backend knowledge in the way RuroTech uses Django, before working on RigAgent.
**Built with:** Claude Code, using narrowly scoped prompts.

---

## How to use this document

Each phase has four parts, and the order matters.

**Read first.** Specific pages, with what to look for. Do this before any code exists. If you skip it, you will not be able to evaluate what Claude Code hands you.

**Build.** What to have Claude Code produce, and how to scope the prompts. Assume one prompt per bullet unless noted.

**Do yourself.** The parts where typing it personally is the point. Mostly shell work, query inspection, and reading generated files. Do not delegate these.

**Comprehension check.** Questions you should be able to answer without looking anything up. If you cannot answer one, you accepted code you do not understand. Go back and ask Claude Code to explain that specific piece before moving on. This is the actual measure of progress, not the number of checklist items ticked.

### The goal is not syntax

You need to know what Django's features do, what they are for, what they offer, and how they interact. You do not need to memorize method signatures. When Claude Code writes something you have not seen, the correct response is "explain what this does and why you chose it," not "looks fine."

### Deadline strategy

Phases 0 through 11 are the spine, targeted for Monday, August 3. Phases 12 through 14 are the tail, for Tuesday and Wednesday or later. The spine is roughly 26 hours of work, which is more than the calendar allows, so expect phases 10 and 11 to be thinner than the rest. That is the intended tradeoff. A working vertical slice you understand beats twelve half-built checklists.

If you fall behind, cut depth from phase 9 (build fewer endpoints, keep the dashboard) before cutting phases 10 or 11 entirely. Ruben named REST, Redis, and Celery as hard requirements, so having each of them working at all matters more than having any one of them polished.

---

## Working with Claude Code on this project

Ruben's guidance was specific: give Claude the context and scope up front so it can make good suggestions, rather than probing it for 45 minutes. Practical version of that:

**Prompt shape that works here.** State the checklist item, the file it belongs in, the convention it must follow, and ask for an explanation alongside the code. Example:

> Add the ModuleListApi endpoint in onboarding/views.py. Follow the HackSoft convention in CLAUDE.md: plain APIView, nested OutputSerializer, no ORM access in the view, read query goes in selectors.py. After the code, explain why the selector returns what it returns and where an N+1 could appear.

**Prompt shape that wastes time.** "How do I build an API in Django." You will get a generic ModelViewSet tutorial that contradicts your conventions.

**Ask for the reasoning, every time.** The habit to build is requesting the explanation in the same prompt as the code. It costs nothing and it is the entire point of this project.

**Push back when it drifts.** Claude Code will occasionally reach for `ModelViewSet`, generics, or business logic in serializers, because that is what most Django code on the internet looks like. When it does, say so and point at CLAUDE.md. Catching that drift is itself a sign you are learning.

**Red flags that mean stop and ask.** Code you cannot explain line by line. A query you cannot predict the SQL for. An endpoint where you do not know how many database queries it fires. Any file you did not read before accepting.

---

## The project domain

Keep this deliberately unglamorous. It is a learning vehicle, and Ruben said not to overthink it.

An internal employee onboarding platform. New hires get assigned onboarding modules covering company policy, security awareness, benefits, and culture, each with a short assessment. They also get non-learning onboarding tasks that require manager approval, like submitting equipment forms or completing I-9 paperwork. There is a company directory with departments and reporting relationships. There is a skills directory where employees describe what they know, searchable by meaning so someone can find help with a vague problem description.

No UI. Every feature is an API endpoint that a React frontend would consume.

### Models

| Model | Purpose | Teaches |
|---|---|---|
| `User` (custom, AbstractUser) | Employees, with `manager` and `department` | Custom user model, self-referential FK |
| `Department` | Org units | Simple FK target |
| `OnboardingModule` | Policy and security content | Choices, ordering |
| `ModuleAssignment` | Who is assigned what, and progress | Through-style FK pair, status choices |
| `Assessment` | Quiz attached to a module | OneToOneField |
| `AssessmentQuestion` | Questions | FK, ordering |
| `AssessmentAttempt` | Every attempt by every user | Volume table, composite index |
| `OnboardingTask` | Non-learning tasks | ManyToMany to Department |
| `TaskAssignment` | Assignment plus approval | Two FKs to User, transaction work |
| `Skill` | Skill with description and embedding | pgvector VectorField, HNSW index |
| `UserSkill` | Explicit through model for User to Skill | ManyToMany with extra fields |
| `ActivityEvent` | Every meaningful user action | Primary volume table, 100k+ rows, JSONField |

### The performance targets these create

- **High-traffic endpoint to optimize tightly:** the onboarding dashboard for the current user. Assigned modules with progress, pending tasks, completion percentage. Would be hit on every page load.
- **Low-traffic endpoint to leave unoptimized on purpose:** a department-wide activity report an admin runs occasionally.
- **Many-to-many read to measure before exposing:** `User` to `Skill` through `UserSkill`.
- **Cursor pagination test case:** `ActivityEvent` ordered by `occurred_at`. Its timestamp is set once on creation, non-null, and effectively unique, which is exactly what DRF requires of a cursor field.
- **Cache target:** the dashboard endpoint, invalidated on module completion and task approval.
- **Vector search:** skill descriptions, queried by a free-text problem statement.

---

# THE SPINE

---

## Phase 0: Context and ground rules

**Time:** 45 min | **Checklist:** 12 (CLAUDE.md) | **Prerequisite for everything else**

This is the phase most people skip and then pay for. You are about to generate a lot of code through Claude Code. The architectural conventions have to exist in writing first, or every prompt re-litigates them.

### Read first

- [HackSoft Django Styleguide](https://github.com/HackSoftware/Django-Styleguide). Read the overview, Services, Selectors, and APIs and Serializers sections properly. Skim the rest. This is your architecture spec for the whole project, and it is the closest published match to what Ruben described.
  - Note their conventions specifically: business logic in `services.py` for writes and `selectors.py` for reads, serializers nested inside the API class as `InputSerializer` and `OutputSerializer`, API naming as `<Entity><Action>Api`, one URL per action, and a deliberate rejection of `ModelViewSet` and generics.
  - Their stated reason for rejecting generics: relying on them fragments business logic across multiple places and makes the data flow hard to trace. That is the same concern Ruben expressed as "views should be slim, services should hold the bulk."
- [Django-Styleguide-Example](https://github.com/HackSoftware/Django-Styleguide-Example). Just browse the structure. You will come back to it in phase 8. Ignore its JWT library choice, which is outdated.

### Build

- **CLAUDE.md at the repo root.** Have Claude Code draft it, then edit it yourself so you know what is in it. It should contain:
  - The domain, in three sentences.
  - The model list and relationships from the table above.
  - Stack: Django 6.0, DRF, Postgres 17 with pgvector, Redis, Celery, Docker Compose.
  - Architecture rules: plain `APIView` only, no `ModelViewSet` or generics. Reads in `selectors.py`, writes in `services.py`. Views do request handling, validation, and response shaping only. No ORM access in views or serializers.
  - Performance rules: one endpoint per data need rather than one endpoint with many optional filters. Return only needed fields. `select_related` and `prefetch_related` chosen per endpoint. Every list endpoint paginated. Be cautious with many-to-many reads.
  - Migrations: `makemigrations` for everything. The pgvector extension migration is the single hand-written exception.
  - Style: no em-dashes in generated content or comments.
  - The endpoint usage table, added to as you build.

### Do yourself

Sketch the models and relationships on paper or in a scratch file before Claude Code touches anything. You do not need it perfect. You need to have thought about it, so that when Claude proposes a schema in phase 4 you have an opinion.

### Comprehension check

1. Why does business logic go in a service rather than in a view or a serializer?
2. What is the difference between a service and a selector, and why separate them at all?
3. What specifically does HackSoft argue you lose by using `ModelViewSet`?
4. In your own words, why does Ruben want many narrow endpoints instead of one flexible one?

---

## Phase 1: Django orientation on SQLite

**Time:** 1.5 hr | **Checklist:** 1 (concepts only)

**Do this in a throwaway directory outside your project, and delete it afterward.** It feels wasteful on a tight clock. It is the highest-value 90 minutes in this plan. You cannot evaluate the Docker setup in phase 3 or the schema in phase 4 if you have never watched a plain Django project work.

**Type this one by hand. Do not use Claude Code.** This is the only phase where that rule applies.

### Read and do

- [Tutorial part 1](https://docs.djangoproject.com/en/6.0/intro/tutorial01/): `startproject`, `startapp`, the file layout, the dev server, a first URL and view.
- [Tutorial part 2](https://docs.djangoproject.com/en/6.0/intro/tutorial02/): models, `makemigrations`, `migrate`, the shell, the admin.
- **Skim parts 3 and 4 without doing them.** Ten minutes. The point is to recognize templates, `render`, and Django forms so that when you see them in a Stack Overflow answer later you know they are not what you are building.
- **Skip parts 5, 6, 7, and 8** for now. Testing comes back in phase 13, admin customization in phase 5.

### Do yourself

- Run `python manage.py migrate` and read the output. Those tables are Django's own.
- Open the generated migration file for your model and read it.
- Open a `manage.py shell` and create, query, and delete an object.

### Comprehension check

1. What is the difference between a project and an app? Can an app live in more than one project?
2. What does `manage.py` give you that `django-admin` does not?
3. What is `INSTALLED_APPS` actually controlling? What happens if you forget to add an app to it?
4. What did `migrate` do on a project with no models of your own yet?
5. Where does the URL-to-view connection actually get made?

Then delete the directory.

---

## Phase 2: Real project skeleton

**Time:** 1 hr | **Checklist:** 1

Now the real repository, at `C:\Projects\Repos\` on your work machine. Still SQLite for one more phase, still no Docker.

### Read first

- [Django settings topic guide](https://docs.djangoproject.com/en/6.0/topics/settings/). How `DJANGO_SETTINGS_MODULE` resolution works, and why settings is just a Python module.
- [Deployment checklist](https://docs.djangoproject.com/en/6.0/howto/deployment/checklist/). Fastest explanation of why `SECRET_KEY`, `DEBUG`, and `ALLOWED_HOSTS` matter.
- [django-environ docs](https://django-environ.readthedocs.io/en/latest/). Look specifically at `env.db()` and `env.cache()`, which parse connection URLs. One library will configure both your Postgres and your Redis from single URL strings, which is exactly the shape Docker Compose wants to inject.

### Build

- Virtual environment, then install Django, `djangorestframework`, `celery`, `redis`, `hiredis`, `django-environ`, `psycopg[binary]`, `pgvector`, `sentence-transformers`, `django-debug-toolbar`, `djangorestframework-simplejwt`.
- Project and app skeleton. Register the app and `rest_framework` in `INSTALLED_APPS`.
- Move `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `DATABASE_URL`, and `REDIS_URL` into `.env`, read through `django-environ`.
- `.env.example` committed, `.env` gitignored.
- `requirements.txt` with pinned versions.
- Git init, `.gitignore`, and your `main` to `dev` to `feature/*` branches.

### Do yourself

- Read `settings.py` top to bottom once. You should recognize every setting or be able to look it up.
- Delete your `SECRET_KEY` from `.env` and start the server. Read the error. Put it back.
- Confirm `git status` shows no `.env`.

### Comprehension check

1. How does Django know which settings module to use?
2. Why is `SECRET_KEY` sensitive? What breaks if it changes on a running production app?
3. What goes wrong if `DEBUG=False` and `ALLOWED_HOSTS` is empty?
4. What does `env.db()` do to a `postgres://` URL, and why is one URL easier to manage than five separate variables?
5. What are `wsgi.py` and `asgi.py` for, and which one would a production server use?

---

## Phase 3: Containerized development environment

**Time:** 2 hr | **Checklist:** 2

### Read first

- [TestDriven.io: Dockerizing Django with Postgres](https://testdriven.io/blog/dockerizing-django-with-postgres-gunicorn-and-nginx/). **Read only the development half and stop before Gunicorn and Nginx.** You do not need a production server for this project. Note that the article predates modern Compose and uses an `entrypoint.sh` polling script to wait for Postgres. You will use Compose healthchecks instead.
- [Docker Compose reference](https://docs.docker.com/compose/), specifically `depends_on` with `condition: service_healthy`, `healthcheck`, and named volumes.
- [pgvector Docker Hub](https://hub.docker.com/r/pgvector/pgvector) for tags.

### Build

- `Dockerfile` for the app. Python 3.12 or later slim base.
- `docker-compose.yml` with three services to start: `web`, `db`, `redis`.
  - **`db` must use `pgvector/pgvector:pg17`, not `postgres:17`.** The extension has to be compiled into the image. This is the single most common way to lose an hour on this project.
  - Named volume for Postgres data.
  - Named volume mounted at the Hugging Face cache path, so the 80MB embedding model is not re-downloaded on every rebuild.
  - `healthcheck` on `db` using `pg_isready`, with `web` waiting on `condition: service_healthy`.
  - Source code bind-mounted into `web` for live reload.
- `.dockerignore`.
- A short `docs/docker.md` or README section with the up, down, rebuild, and shell commands.

**Scope the compose file as one prompt, then follow with explanation prompts.** This is the first place to lean on Claude Code properly, because no single tutorial covers this service combination and the ones that come close are outdated.

### Do yourself

- Read the whole compose file and Dockerfile before running anything.
- `docker compose up`, then `docker compose exec web python manage.py migrate`.
- `docker compose exec db psql -U <user> -d <db> -c "SELECT * FROM pg_available_extensions WHERE name = 'vector';"` and confirm you get a row. If you do not, your image is wrong.
- Stop everything, `docker compose down`, bring it back up, confirm your data survived.

### Comprehension check

1. Why is your database host `db` and not `localhost` inside the container?
2. What does the source code bind mount buy you in development, and why would you not want it in production?
3. Why does `depends_on` alone not guarantee the database is ready?
4. What does the named volume do that a container filesystem does not?
5. Why does the Postgres image need to be the pgvector one rather than the stock image?
6. What does `.dockerignore` change about your build?

---

## Phase 4: Schema design and first migration

**Time:** 3.5 hr | **Checklist:** 3

The highest-value phase in the project. Ruben said the models and ORM section shows how the data is actually used, and he was right. Do not rush this.

### Read first

- [Models topic guide](https://docs.djangoproject.com/en/6.0/topics/db/models/). Read it fully, not as reference.
- [Model field reference](https://docs.djangoproject.com/en/6.0/ref/models/fields/). Focus on `null` versus `blank`, `choices`, and every `on_delete` option.
- [Customizing authentication](https://docs.djangoproject.com/en/6.0/topics/auth/customizing/). The custom user model section.
- [Meta options](https://docs.djangoproject.com/en/6.0/ref/models/options/), [constraints](https://docs.djangoproject.com/en/6.0/ref/models/constraints/), [indexes](https://docs.djangoproject.com/en/6.0/ref/models/indexes/).
- [Migrations topic guide](https://docs.djangoproject.com/en/6.0/topics/migrations/).
- [pgvector-python](https://github.com/pgvector/pgvector-python), Django section. `VectorField(dimensions=384)`, `VectorExtension()` for the migration, `HnswIndex` with `opclasses=['vector_cosine_ops']`.
- HackSoft's Models section on where validation belongs. Their rule: model `clean` for simple multi-field non-relational validation, service layer when validation is complex or spans relations, and database constraints wherever possible because there is less code to maintain and the data is protected regardless of what wrote it.

### Build, in this exact order

1. **The custom user model first.** `AbstractUser` subclass, with `manager` as a self-referential FK and `department` as an FK. Set `AUTH_USER_MODEL` in settings. **Nothing else happens until this is done.** Django's docs recommend a custom user model on every new project precisely because changing `AUTH_USER_MODEL` after tables exist is significantly harder, given its effect on foreign keys and many-to-many relationships.
2. The rest of the models from the domain table. Work through them with Claude Code as a conversation, not a single prompt. Discuss `on_delete` for each relationship.
3. `__str__` and `Meta.ordering` on every model.
4. `related_name` on every relationship.
5. A model method and a model property that derive values from fields. Good candidates: `ModuleAssignment.is_overdue` as a property, `User.get_direct_reports()` as a method.
6. A custom manager or queryset holding a reusable filter. Good candidate: `ModuleAssignmentQuerySet.incomplete()`.
7. `db_index` on frequently filtered fields, and a composite `Meta.indexes` entry on `ActivityEvent` covering `user` and `occurred_at` descending.
8. A unique constraint and a check constraint via `Meta.constraints`. Candidates: unique together on `UserSkill` for user and skill, check constraint that `AssessmentAttempt.score` is between 0 and 100.
9. **The pgvector extension migration.** `python manage.py makemigrations <app> --empty --name enable_pgvector`, then add `VectorExtension()` to its operations. This must run before the migration that creates the vector column.
10. `HnswIndex` on `Skill.embedding` with cosine opclasses.
11. `makemigrations` and `migrate`.
12. Add one field to an existing model and migrate again.

### Do yourself

- **Read every generated migration file.** All of them. This is where you learn what the ORM is actually doing.
- Open `psql` and run `\d+ <table>` on three tables. Compare what you see to your model definitions.
- Confirm the vector extension is installed: `\dx`.

### Comprehension check

1. Why must `AUTH_USER_MODEL` be set before the first `migrate`? What specifically breaks if you change it later?
2. Explain the difference between `on_delete=CASCADE`, `PROTECT`, `SET_NULL`, and `DO_NOTHING`, and name a relationship in your schema where each would be the right answer.
3. What is the difference between `null=True` and `blank=True`?
4. What does `related_name` change, and what is the reverse accessor called if you omit it?
5. Why does the pgvector extension need a hand-written migration when nothing else does?
6. What is the difference between a `db_index` on two fields separately and a composite index on both?
7. Where should validation live: the model's `clean`, a database constraint, or a service? Give an example of each.

---

## Phase 5: Django Admin

**Time:** 1 hr | **Checklist:** 4

Ruben's stated reason for keeping this: it stops you relying solely on Postman to look at models and data. That value is highest now, while you are about to write a lot of queries, not at the end.

### Read first

- [Admin reference](https://docs.djangoproject.com/en/6.0/ref/contrib/admin/). You only need `list_display`, `list_filter`, `search_fields`, `readonly_fields`, `date_hierarchy`, `list_select_related`, and inlines.
- [Tutorial part 7](https://docs.djangoproject.com/en/6.0/intro/tutorial07/) for a worked example.
- The `UserAdmin` subclassing section of the customizing-authentication page, since a custom user model needs it.

### Build

- Superuser, and confirm login.
- Register all models.
- One fully customized `ModelAdmin` on `ActivityEvent` or `AssessmentAttempt`, with `list_display`, `list_filter`, `search_fields`, `date_hierarchy`, and `list_select_related`.
- An inline for `AssessmentQuestion` inside `Assessment`.
- `readonly_fields` where it makes sense, such as `occurred_at`.

### Do yourself

- Create a handful of records by hand through the admin. You want a few real rows before phase 6 generates 100,000 fake ones.
- Load an admin list page for a model with a foreign key, then add `list_select_related` and reload. If you have the Debug Toolbar running, watch the query count drop. The admin is the one place in this project where the toolbar renders properly, because admin pages are HTML.

### Comprehension check

1. Why does a custom user model require its own `UserAdmin`?
2. What is `list_select_related` fixing, and what is the underlying problem called?
3. When would an inline be the wrong choice?

---

## Phase 6: Seed data at volume

**Time:** 1.5 hr | **Checklist:** 5 (first item), embeddings

You need real volume before the ORM phase or none of the performance lessons will be visible. At 20 rows, every query looks fast and every index looks pointless.

### Read first

- [all-MiniLM-L6-v2 model card](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2). 384 dimensions, roughly 22 million parameters, around 14,000 sentences per second on a plain CPU, about 80MB on disk. It falls back to CPU automatically when CUDA is absent with no code changes, which is why you are not doing GPU passthrough. Its output is already normalized.
- [Writing custom management commands](https://docs.djangoproject.com/en/6.0/howto/custom-management-commands/).
- [`bulk_create` in the QuerySet reference](https://docs.djangoproject.com/en/6.0/ref/models/querysets/).

### Build

- **An embedding provider function**, shaped as `embed_texts(texts: list[str]) -> list[list[float]]`. This is the swappability contract: the call site never changes if you later move to an API. Put the model name and dimension count in settings constants.
  - Be aware of the limit of that abstraction. Vector dimension is baked into the database column. MiniLM is 384, OpenAI's small model is 1536. Swapping providers later is a migration plus a re-embed, not a config change. The settings constant is the most you can do to soften it.
- **A `seed_data` management command** that generates:
  - Departments, then users with a valid manager hierarchy (no cycles, one or two users with no manager at the top).
  - Onboarding modules with assessments and questions.
  - Onboarding tasks, some requiring approval.
  - Module assignments and task assignments across users, with a realistic mix of statuses.
  - Assessment attempts, several thousand, with a believable pass and fail and retake distribution.
  - Skills with real-sounding descriptions, embedded via `embed_texts`.
  - **`ActivityEvent` rows, 100,000 or more**, spread across a date range, using `bulk_create` in batches.
  - An `--events` argument so you can control the volume.

Prompt this as two or three separate prompts, not one. Ask why batching matters when you get the `bulk_create` code.

### Do yourself

- Run the command and time it. Then run it with the batch size set to 1 and watch the difference.
- In `psql`, `SELECT count(*) FROM <activity table>;` and confirm your volume.
- In the shell, fetch one `Skill` and print `len(skill.embedding)`. Confirm 384.

### Comprehension check

1. Why does `bulk_create` need a batch size at all? What happens without one on 100,000 rows?
2. What does `bulk_create` skip that a loop of `.save()` calls would do?
3. Why 384, and what would you have to do to move to a 1536-dimension model?
4. What is the difference between `bulk_create` and `update_or_create`, and when is each right?

---

## Phase 7: ORM deep work in the shell

**Time:** 4 hr | **Checklist:** 5

The biggest phase, and the one to protect if the schedule slips. **Do almost all of this by hand in `manage.py shell`.** Claude Code is for explaining results, not producing queries. You will not learn the ORM by reading generated querysets.

### Read first

- [Making queries](https://docs.djangoproject.com/en/6.0/topics/db/models/) if you have not already, and the [QuerySet API reference](https://docs.djangoproject.com/en/6.0/ref/models/querysets/) as your working reference.
- [Database access optimization](https://docs.djangoproject.com/en/6.0/topics/db/optimization/). **This is the most important single page for Ruben's requirements.** Its section list reads like your Checklist 7: profile first, understand QuerySet evaluation, use `iterator()`, use `explain()`, do database work in the database rather than in Python, do not retrieve things you do not need, use `values()` and `values_list()`, use `defer()` and `only()`.
  - Note the warning that `defer()` and `only()` become a pessimization if used badly, because the ORM has to fetch the omitted columns in a separate query if you later touch them. That is your concrete example of why the checklist says benchmark rather than assume.
- [Aggregation](https://docs.djangoproject.com/en/6.0/topics/db/aggregation/) for `annotate` versus `aggregate`, which is the distinction most people get wrong.
- [Query expressions](https://docs.djangoproject.com/en/6.0/ref/models/expressions/) for `F`, `Window`, and `Subquery`.

### Do yourself, in the shell

Work through these in order. After each, print the generated SQL with `.query` or `print(qs.query)`.

1. `filter`, `exclude`, `get`, `order_by`, `count`, `values`, `values_list`.
2. Reverse traversal using a `related_name` you defined.
3. Double-underscore lookups spanning relationships, at least two levels deep.
4. `Q` objects for an OR condition. `F` expressions comparing two fields on the same row.
5. `annotate` to add a per-user completion count. `aggregate` to get a project-wide average score. Be able to state the difference.
6. `only()` and `defer()` on a wide model. Then deliberately access a deferred field and watch the extra query fire.
7. `iterator()` over your full `ActivityEvent` table. Compare memory behavior to a plain queryset.
8. **Latest record per group.** The latest `ActivityEvent` per user. Do it three ways: a naive Python loop, `Subquery` with `OuterRef`, and Postgres `DISTINCT ON` via `.order_by('user', '-occurred_at').distinct('user')`. This is the hardest query in the project.
9. **Trigger an N+1 on purpose.** Loop over module assignments printing `assignment.user.email`. Count the queries. Fix with `select_related`. Then do the many-to-many version with user skills and fix with `prefetch_related`.
10. Shape a `values()` result into plain dicts ready for a JSON response.
11. **Vector similarity query.** Embed a free-text problem statement and find the nearest skills with `CosineDistance` and `order_by`.

### Use Claude Code for

- **Step 8 specifically.** Ask for all three approaches side by side, then run `EXPLAIN ANALYZE` on each yourself and compare the plans. Web tutorials on this pattern are mostly poor.
- Explaining any query plan you cannot read.

### Then, in psql

- `EXPLAIN ANALYZE` your slowest query. Read the plan. Identify whether it used an index or did a sequential scan.
- `EXPLAIN ANALYZE` a query that filters on your composite index and confirm the index is being used. If it is not, work out why.
- `EXPLAIN ANALYZE` the vector query and confirm the HNSW index is being used rather than a sequential scan.

### Comprehension check

1. When is a queryset actually evaluated? Name three things that trigger it.
2. `select_related` versus `prefetch_related`: what does each do at the SQL level, and why can `select_related` not handle many-to-many?
3. What does `annotate` return that `aggregate` does not?
4. When is `only()` a pessimization?
5. What is the N+1 problem, in one sentence, and how would you spot it in a query log?
6. Why is `DISTINCT ON` Postgres-specific, and what would you do on a database that lacked it?
7. Looking at an `EXPLAIN ANALYZE` plan, how do you tell whether your index was used?

---

## Phase 8: First vertical slice, one endpoint

**Time:** 2.5 hr | **Checklist:** 6, plus the request-trace item from 10

One endpoint, built properly, understood completely. Do not build a second one until you can trace this one end to end from memory.

### Read first

- [HackSoft styleguide](https://github.com/HackSoftware/Django-Styleguide), the APIs and Serializers section, properly this time. Their specific conventions:
  - Serializers nested inside the API class, named `InputSerializer` or `OutputSerializer`. `OutputSerializer` may subclass `ModelSerializer`. `InputSerializer` should always be a plain `Serializer`.
  - Reuse serializers as little as possible, because reuse exposes you to surprises when a base serializer changes. Use their `inline_serializer` helper for nesting.
  - API naming `<Entity><Action>Api`, one URL per action, URLs grouped into per-domain pattern lists and included from `urlpatterns`.
  - Class-based APIs by default, so you can inherit a `BaseApi` or add mixins.
- [Django-Styleguide-Example](https://github.com/HackSoftware/Django-Styleguide-Example), the actual code for a list API and a detail API.
- [DRF serializers](https://www.django-rest-framework.org/api-guide/serializers/) and [APIView](https://www.django-rest-framework.org/api-guide/views/).
- [cdrf.co](https://cdrf.co) as a reference for what any DRF class actually exposes.

### Build

- `views.py`, `selectors.py`, `services.py`, and `urls.py` in your app.
- **`ModuleListApi`**: plain `APIView`, `get` handler, nested `OutputSerializer`, read query in a `module_list()` selector. No ORM access in the view.
- URL wired through `include()`, named, referenced by name.
- **`ModuleDetailApi`**: separate class, path parameter, its own selector.
- Correct status codes via DRF `Response`.

### Do yourself

- **Trace one request end to end and write it down.** URL resolution, `APIView.dispatch`, the `get` handler, the selector, the ORM query, the SQL, the serializer, the `Response`, the rendered JSON. This single exercise is the best comprehension check in the whole project.
- Hit both endpoints from Postman or `curl`.
- Count the queries each one fires.

### Comprehension check

1. Walk through everything that happens between the HTTP request arriving and JSON coming back.
2. What does `APIView` do that a plain Django view does not?
3. Why is the serializer nested inside the API class rather than in a shared `serializers.py`?
4. Why does the view not touch the ORM, when doing so would be fewer lines of code?
5. What is the difference between an `InputSerializer` and an `OutputSerializer`, and why is one a plain `Serializer` while the other can be a `ModelSerializer`?

---

## Phase 9: Endpoint suite with the performance lens

**Time:** 4.5 hr | **Checklist:** 6 and 7 together

**Checklist 7 is not a phase, it is a lens.** Every performance item is a decision you make while writing a given endpoint, not a cleanup pass afterward. That is the habit Ruben described.

### Read first

- [Database access optimization](https://docs.djangoproject.com/en/6.0/topics/db/optimization/), again, now as a working checklist.
- [DRF pagination](https://www.django-rest-framework.org/api-guide/pagination/). **Read the note that pagination is only automatic on generic views and viewsets, and that with a plain `APIView` you must call into the pagination API yourself.** This is why your checklist specifies a `get_paginated_response` helper.
  - Also read the cursor pagination requirements: the ordering field should be unchanging and set once on creation, unique or nearly unique, non-nullable, coercible to a string, and never a float, because precision errors produce incorrect results. Your `ActivityEvent.occurred_at` satisfies all of these.
- HackSoft's List APIs section, which names this exact problem and resolves it: selectors do the actual filtering, APIs handle filter parameter serialization, and the API applies DRF pagination through a helper.
- [Django cache framework](https://docs.djangoproject.com/en/6.0/topics/cache/). Django has had a built-in Redis backend since 4.0, so you are using `django.core.cache.backends.redis.RedisCache`, not a third-party package.
- [django-debug-toolbar installation](https://django-debug-toolbar.readthedocs.io/en/latest/installation.html). Use `debug_toolbar.middleware.show_toolbar_with_docker` as your `SHOW_TOOLBAR_CALLBACK` rather than the `socket.gethostbyname_ex` hack most tutorials show. Do not enable the toolbar while running tests.
- [Django testing tools](https://docs.djangoproject.com/en/6.0/topics/testing/tools/), the `assertNumQueries` section only.

### Build

**Shared infrastructure first:**
- `api/pagination.py` with a `get_paginated_response` helper.
- `api/exception_handlers.py` with a custom DRF exception handler, plus a custom application exception class translated to an HTTP status in one place.
- Debug Toolbar configured for Docker.
- Redis cache configured through `env.cache()`.

**Then the endpoints, each with its performance decisions made deliberately:**

| Endpoint | Teaches |
|---|---|
| `ActivityEventListApi` | Cursor pagination on a large table, `FilterSerializer`, filtering in the selector |
| `UserDetailApi` | The full object |
| `UserSkillsApi` | A related subset as its own endpoint, not a filter parameter |
| `UserReportsApi` | Another slice, direct manager and direct reports only |
| `MyDashboardApi` | **The high-traffic endpoint. Optimize tightly, cache in Redis, minimum queries.** |
| `DepartmentActivityReportApi` | **The low-traffic endpoint. Leave it unoptimized on purpose and write down why.** |
| `SkillSearchApi` | Vector similarity search |
| `TaskApprovalApi` | POST, `InputSerializer`, a service coordinating `TaskAssignment` and `ActivityEvent` inside `transaction.atomic` |

**Then the measurement work:**
- `assertNumQueries` around your optimized endpoints, locking in the counts.
- Measure the `UserSkills` many-to-many read before you are satisfied with it.
- Compare `PageNumberPagination` against `CursorPagination` on a deep page of `ActivityEvent`. Time both.
- Cache the dashboard, measure the difference, then define the key strategy and the invalidation triggers.
- Add or adjust indexes based on the filters these endpoints actually use, then verify with `EXPLAIN ANALYZE`.
- **Fill in the endpoint usage table in CLAUDE.md**: every endpoint, its purpose, its expected traffic, and the optimization level that justifies.

### Use Claude Code for

**The cache key strategy and invalidation triggers.** This is genuinely project-specific and there is no useful general tutorial, because the answer depends entirely on which writes stale which reads. Give it the dashboard selector and the write paths, and work it out together.

### Do yourself

- Every `assertNumQueries` number. Guess the count before you run it.
- The pagination timing comparison.
- The before and after cache timing.

### Comprehension check

1. Why is `UserSkillsApi` a separate endpoint instead of `?include=skills` on the user detail endpoint?
2. Why does pagination not work automatically on your endpoints, and what does the helper do?
3. What makes a field suitable as a cursor pagination key, and why is a float disqualified?
4. Why is offset pagination slow on page 5,000 of a large table?
5. What stales your dashboard cache, and how does your invalidation handle it?
6. Which of your endpoints would you optimize further if traffic tripled, and which would you leave alone? Why?
7. Why does the Debug Toolbar not appear on your JSON responses?

---

## Phase 10: Authentication

**Time:** 2.5 hr | **Checklist:** 8 (2FA deferred)

### Read first

- [Simple JWT docs](https://django-rest-framework-simplejwt.readthedocs.io/en/stable/), the settings page and the blacklist app page.
  - Rotation and blacklisting are two settings, not one. `BLACKLIST_AFTER_ROTATION` only does anything when `ROTATE_REFRESH_TOKENS` is also True and `rest_framework_simplejwt.token_blacklist` is in `INSTALLED_APPS`.
  - Defaults are a 5 minute access token and a 1 day refresh token.
  - **Read the `UPDATE_LAST_LOGIN` warning.** The docs state it dramatically increases database transactions, that abuse of the views could slow the server, that this is a potential security vulnerability, and that you should throttle the endpoint at minimum. That one setting connects your throttling item, your performance discipline, and a real security concern. Use it as the actual justification for the throttle rather than adding throttling as a checkbox.
- [DRF authentication](https://www.django-rest-framework.org/api-guide/authentication/), [permissions](https://www.django-rest-framework.org/api-guide/permissions/), [throttling](https://www.django-rest-framework.org/api-guide/throttling/).

### Build

- Simple JWT configured, with `SIGNING_KEY` from its own environment variable rather than reusing `SECRET_KEY`. That way you can invalidate every token by rotating one value without disturbing everything else that depends on `SECRET_KEY`.
- Token obtain and token refresh endpoints.
- Access and refresh lifetimes set deliberately, and be able to justify the numbers.
- `ROTATE_REFRESH_TOKENS` and `BLACKLIST_AFTER_ROTATION` on, with the blacklist app installed and migrated.
- DRF default authentication and permission classes set in settings. This is also what makes `IsAuthenticated` real for the first time. Every endpoint in CLAUDE.md's permissions table has been running without it, so confirm each one still behaves the way that table says once auth is live.
- **Close out every row marked OPEN in CLAUDE.md's permissions table, one at a time:**
  - `MyDashboardApi`: drop the `user_id` query parameter, read `request.user` instead. This also changes the cache key, since the key is currently derived from the parameter, not the authenticated caller.
  - `ActivityEventListApi`: self by default, a manager may filter to one direct report, staff unrestricted. This scoping logic is genuinely new, not a rename of the existing filter.
- **`TaskApprovalApi` needs less new work than it looks like.** The selector already scopes to `assignee__manager_id == request.user.id` and 404s a mismatch, done in Phase 9 ahead of auth existing to enforce it against. What Phase 10 actually adds is the permission class layer, since `check_object_permissions` is not automatic on a plain `APIView` (gotcha 15), plus wiring `request.user` into the selector call now that there is a real one. Do not re-derive the scoping query, it already exists in `selectors/onboarding_tasks.py`.
- `DepartmentActivityReportApi`: staff only, checked via `request.user.is_staff`. There is no dedicated selector scope here, since once the caller is staff the read is unscoped, so this is entirely a permission class decision.
- Decide, and record the decision, whether `UserDetailApi` needs to trim any field for a non-staff caller now that "who is asking" is a real thing instead of a hypothetical.
- `ActivityEvent` attached to `request.user` on creation.
- Redis-backed throttling on the auth endpoints.
- Confirm no session login or logout views remain.
- Update both tables in CLAUDE.md, the endpoints table and the permissions table, so every row that was OPEN or Intent now reads as done, with the actual mechanism recorded rather than the plan for it.

### Use Claude Code for

The `ActivityEventListApi` manager-can-view-one-direct-report scoping. That rule is domain logic specific to this project, not a documented pattern, and it is the one piece of this phase that is not just "turn on the auth that was always intended." For `TaskApprovalApi`, the conversation is narrower: what belongs in the permission class given the selector already does the scoping, so you do not end up duplicating the `assignee__manager_id` check in both places.

### Do yourself

- The full refresh flow from Postman. Get a token pair, use the access token, wait for it to expire or set a 10 second lifetime to force it, get a 401, refresh, confirm the old refresh token is now rejected.
- Decode an access token at jwt.io and read the claims.
- Hit an auth endpoint repeatedly until the throttle fires.

### Comprehension check

1. What is in an access token, and how does the server verify it without a database lookup?
2. Why have refresh tokens at all, instead of one long-lived access token?
3. What does rotation plus blacklisting protect against that rotation alone does not?
4. Why is blacklisting a database operation when JWT verification is not?
5. Why does `UPDATE_LAST_LOGIN` need a throttle?
6. Where does per-user scoping belong, and why not in the permission class?

---

## Phase 11: Celery, thin slice

**Time:** 2 hr | **Checklist:** 9 (partial)

Get one task genuinely working end to end. Depth comes in phase 12.

### Read first

- [Celery first steps with Django](https://docs.celeryq.dev/en/stable/django/first-steps-with-django.html) and the [official Django example project](https://github.com/celery/celery/tree/main/examples/django/).
  - Celery has supported Django natively since 3.1, so no bridge library. You add a `celery.py` to the project package, point it at Django settings with the `CELERY_` namespace, and call `autodiscover_tasks` so it finds `tasks.py` in every installed app. Use `@shared_task`.
  - **Read the transaction pitfall section.** Celery's own docs warn that triggering a task without waiting for the end of the database transaction means the task may run before changes are persisted.
- [TestDriven.io: Asynchronous Tasks with Django and Celery](https://testdriven.io/blog/django-and-celery/).

### Build

- `celery.py` in the project package, Redis as broker and result backend, both from environment variables.
- `celery-worker` service added to compose.
- **`generate_skill_embedding(skill_id)`** as your first task. It is the slow operation, and it is a natural fit because the model call is CPU-bound and you do not want it in the request cycle.
- Triggered from a service function, returning a response immediately.
- **Enqueued with `transaction.on_commit`.** Your Checklist 6 wraps writes in `transaction.atomic` and your Checklist 9 triggers tasks from services. Do both naively and the worker fetches a row that has not committed yet, gets a `DoesNotExist`, and you have an intermittent bug that will not reproduce reliably. This is the same underlying issue as passing IDs rather than instances: the worker is a separate process with its own connection and its own view of committed state.
- Store and retrieve a task result.

### Do yourself

- Watch the worker logs while you trigger a task.
- Deliberately break it: enqueue with `.delay()` directly instead of `on_commit`, inside an `atomic` block, and try to make the worker fail. Then fix it. This bug is worth meeting on purpose in a sandbox rather than in production.
- Try passing a model instance as a task argument and read the error.

### Comprehension check

1. Why can a task run before the data it needs exists?
2. Why pass an ID rather than a model instance? Name two distinct reasons.
3. What is a broker doing, and what is a result backend doing? Why can both be Redis?
4. What does `autodiscover_tasks` do, and what breaks without it?
5. What happens to a queued task if the worker restarts?

---

# THE TAIL

Tuesday, Wednesday, and beyond. Ruben confirmed this project has no completion date, so this section stays live.

---

## Phase 12: Celery, in full

**Time:** 2.5 hr | **Checklist:** 9

### Read first

- [Celery tasks reference](https://docs.celeryq.dev/en/stable/userguide/tasks.html) for `autoretry_for`, `retry_backoff`, `max_retries`, `time_limit`, and `soft_time_limit`.
- [TestDriven.io: Handling Periodic Tasks with Celery and Docker](https://testdriven.io/blog/django-celery-periodic-tasks/), which adds worker, beat, and Redis containers to an existing Django compose setup.
- [Flower docs](https://flower.readthedocs.io/).

### Build

- `celery-beat` and `flower` services in compose.
- **`send_overdue_reminders()`** with retries and exponential backoff, since notification sends fail transiently.
- **`score_assessment_attempt(attempt_id)`**, made idempotent so running it twice is safe.
- **`rollup_department_progress()`** as a periodic task on beat.
- Task time limits set, and one task routed to a dedicated queue.

### Use Claude Code for

**Idempotency.** This is the subtlest item on the entire checklist and most Celery tutorials do not touch it. Have Claude walk you through why `get_or_create` is not automatically idempotent under concurrency, and how a unique constraint plus a caught `IntegrityError` differs from check-then-insert.

### Comprehension check

1. What makes a task idempotent? Why is `get_or_create` not enough?
2Better. What is the difference between `time_limit` and `soft_time_limit`?
3. Why route a task to a dedicated queue?
4. What does beat do if the scheduler was down when a task was due?

---

## Phase 13: Testing

**Time:** 3 hr | **Checklist:** 10

Ruben's framing: important for smaller projects, awkward around the multi-tenant middleware patterns their real codebase uses, and their full suite is large enough that they no longer run it locally. So test properly here, but leave middleware and multi-tenant testing out of scope entirely.

### Read first

- [Django testing tools](https://docs.djangoproject.com/en/6.0/topics/testing/tools/) and [advanced testing topics](https://docs.djangoproject.com/en/6.0/topics/testing/advanced/).
- [DRF testing](https://www.django-rest-framework.org/api-guide/testing/) for `APIClient` and `force_authenticate`.
- [factory_boy](https://factoryboy.readthedocs.io/), plus HackSoft's articles on [fakes and factories](https://www.hacksoft.io/blog/improve-your-tests-django-fakes-and-factories) and [advanced usage](https://www.hacksoft.io/blog/improve-your-tests-django-fakes-and-factories-advanced-usage). Their example repo has working code for both.

### Build

- Test database against the containerized Postgres. **The test database also needs the pgvector extension**, which your extension migration handles automatically since Django runs migrations to build the test database.
- Tests pointed at a separate Redis database or the local memory cache.
- Model tests for methods, properties, and constraints. Assert that your check constraint actually rejects a bad score.
- Unit tests for services and selectors, called directly rather than through a view. **This is the real payoff of the service layer** and the reason the architecture is worth the extra files.
- Integration tests per endpoint, success and failure paths.
- Query parameter edge cases: missing, empty, non-numeric, above maximum.
- Auth and permission enforcement tests, including that a manager cannot approve a peer's task, that a manager can view one direct report's activity feed but not an unrelated user's, and that `DepartmentActivityReportApi` rejects a non-staff caller.
- `assertNumQueries` locking in your optimized endpoint counts.
- factory_boy factories.
- Celery task tests with `CELERY_TASK_ALWAYS_EAGER`, and by calling task functions directly.
- **`captureOnCommitCallbacks(execute=True)`** where you test `on_commit` enqueueing.

### The gotcha to expect

Django's `TestCase` wraps each test in a transaction that is rolled back, which means `on_commit` callbacks never fire. Once you correctly switch to `transaction.on_commit` in phase 11, your task-triggering tests will silently stop testing anything. `captureOnCommitCallbacks` is the fix. Meet this on purpose rather than as a mystery.

Related: `CELERY_TASK_ALWAYS_EAGER` runs tasks inline, which is convenient but means you are not exercising task argument serialization. Use eager mode for most tests and direct calls where you want to assert on logic.

### Use Claude Code for

The factories. `factory_boy` with a self-referential manager hierarchy needs careful `SubFactory` handling to avoid infinite recursion, which is fiddly boilerplate rather than a learning opportunity.

### Do yourself

- Make one test fail on purpose and read the whole output.
- Guess each `assertNumQueries` number before running it.

### Comprehension check

1. Why is testing a selector directly more valuable than testing it through a view?
2. Why do `on_commit` callbacks not fire under `TestCase`?
3. What does `CELERY_TASK_ALWAYS_EAGER` hide?
4. What is `assertNumQueries` protecting you from in the future?

---

## Phase 14: CI/CD and documentation

**Time:** 3 hr | **Checklist:** 11 and 12

### Read first

- [GitHub: using containerized services](https://docs.github.com/en/actions/using-containerized-services), with its dedicated PostgreSQL and Redis guides.
- [Building and testing Python](https://docs.github.com/en/actions/automating-builds-and-tests/building-and-testing-python).
- [drf-spectacular customization guide](https://drf-spectacular.readthedocs.io/en/latest/customization.html) and [FAQ](https://drf-spectacular.readthedocs.io/en/latest/faq.html).

### Build

- `.github/workflows/ci.yml` running on push and pull request.
- **Postgres service container using `pgvector/pgvector:pg17`, not the stock `postgres` image.** Every tutorial you find uses `postgres`, and copying that makes your migrations fail in CI while passing locally. Also ignore the common advice to use the runner's preinstalled Postgres or to swap to SQLite in CI. Both break pgvector.
- Redis service container.
- Health check options on both, since service containers start before they accept connections. `pg_isready` for Postgres, `redis-cli ping` for Redis. Service containers require an Ubuntu runner.
- Migrations and the test suite in CI.
- Linting and formatting checks. Ruff is the fast default.
- Dependency caching.
- Branch protection requiring the workflow to pass before merging into `dev`.
- A deploy step, even against a stub, so you have seen the full pipeline shape.
- Status badge in the README.
- README covering setup, environment variables, and Docker commands.
- Celery task documentation: each task, its schedule, its queue, and its retry behavior.
- The Django request cycle summary for the Trello card.

### On drf-spectacular, deliberately last

drf-spectacular generates schemas by introspecting `serializer_class` and `queryset` on the view. Its docs are direct that patterns like plain `APIView` provide very little discoverable information, and its FAQ has an entry titled "Using @extend_schema on APIView has no effect."

Because you are building HackSoft-style plain `APIView` classes with nested serializers, you will get a nearly empty schema unless you decorate every endpoint with `@extend_schema(request=..., responses=...)`. That is doable, and `@extend_schema` does support APIView, but it is one decorator per endpoint rather than a one-line install. There is also a known naming collision between HackSoft's `inline_serializer` helper and drf-spectacular that needs unique serializer names.

This teaches you almost nothing about Django and costs real time. Do it last, or not at all before you have working CI.

### Comprehension check

1. Why does the CI Postgres service need the pgvector image?
2. What does the health check option change about job timing?
3. What is the difference between building the image in CI and running tests in CI?
4. Why does drf-spectacular struggle with your architecture?

---

## Deferred, tracked so nothing gets lost

Not abandoned, just not before the deadline.

- Two-factor authentication on login. If you pick this up, the [Appliku JWT plus 2FA tutorial](https://appliku.com/post/how-use-jwt-authentication-django/) and its [repo](https://github.com/appliku/djangojwt2fa) are the only decent combined resource found. Be aware that 2FA sits awkwardly with stateless JWT, since it forces a two-step login flow.
- drf-spectacular OpenAPI docs, per the reasoning above.
- Full org chart traversal. Walking an arbitrary-depth hierarchy needs a recursive CTE, which the Django ORM does not do without raw SQL or a third-party package. A great lesson in where the ORM stops, and a bad use of a deadline day. Direct manager and direct reports only for now.
- django-filter, pending Ruben's answer on whether RuroTech uses it. If yes, it returns as a FilterSet instantiated inside the selector, not as a `filter_backends` entry on the view.
- GPU embeddings. Your 5080 Ti would fly, but WSL2 plus the NVIDIA container toolkit plus CUDA torch adds gigabytes to the image and minutes to every rebuild, for a workload CPU handles in seconds.

---

## Three questions still worth asking Ruben

None of these block you, all three would sharpen the work.

1. **Does RuroTech use django-filter?** Changes phases 8 and 9.
2. **Plain APIView, or DRF generics and ViewSets?** You have been told to use DRF but not which style. The HackSoft convention matches his slim-views instruction exactly, which is why this roadmap uses it. If the team actually uses `ModelViewSet`, you would be learning the opposite of production.
3. **What is pgvector actually used for at RuroTech?** The skill search feature here is a plausible invention. Knowing their real use case would make phases 6 and 7 far more transferable.

---

## Resource index

**Django core**
- Tutorial: https://docs.djangoproject.com/en/6.0/intro/tutorial01/
- Models: https://docs.djangoproject.com/en/6.0/topics/db/models/
- QuerySet reference: https://docs.djangoproject.com/en/6.0/ref/models/querysets/
- Database access optimization: https://docs.djangoproject.com/en/6.0/topics/db/optimization/
- Aggregation: https://docs.djangoproject.com/en/6.0/topics/db/aggregation/
- Query expressions: https://docs.djangoproject.com/en/6.0/ref/models/expressions/
- Migrations: https://docs.djangoproject.com/en/6.0/topics/migrations/
- Constraints: https://docs.djangoproject.com/en/6.0/ref/models/constraints/
- Indexes: https://docs.djangoproject.com/en/6.0/ref/models/indexes/
- Custom user models: https://docs.djangoproject.com/en/6.0/topics/auth/customizing/
- Admin: https://docs.djangoproject.com/en/6.0/ref/contrib/admin/
- Settings: https://docs.djangoproject.com/en/6.0/topics/settings/
- Deployment checklist: https://docs.djangoproject.com/en/6.0/howto/deployment/checklist/
- Cache framework: https://docs.djangoproject.com/en/6.0/topics/cache/
- Transactions: https://docs.djangoproject.com/en/6.0/topics/db/transactions/
- Testing tools: https://docs.djangoproject.com/en/6.0/topics/testing/tools/
- Management commands: https://docs.djangoproject.com/en/6.0/howto/custom-management-commands/

**Architecture**
- HackSoft Django Styleguide: https://github.com/HackSoftware/Django-Styleguide
- Styleguide Example: https://github.com/HackSoftware/Django-Styleguide-Example
- Fakes and factories: https://www.hacksoft.io/blog/improve-your-tests-django-fakes-and-factories

**DRF**
- Serializers: https://www.django-rest-framework.org/api-guide/serializers/
- APIView: https://www.django-rest-framework.org/api-guide/views/
- Pagination: https://www.django-rest-framework.org/api-guide/pagination/
- Permissions: https://www.django-rest-framework.org/api-guide/permissions/
- Throttling: https://www.django-rest-framework.org/api-guide/throttling/
- Testing: https://www.django-rest-framework.org/api-guide/testing/
- Class reference: https://cdrf.co

**Infrastructure**
- Docker Compose: https://docs.docker.com/compose/
- TestDriven Django on Docker: https://testdriven.io/blog/dockerizing-django-with-postgres-gunicorn-and-nginx/
- pgvector: https://github.com/pgvector/pgvector
- pgvector-python: https://github.com/pgvector/pgvector-python
- pgvector images: https://hub.docker.com/r/pgvector/pgvector
- django-environ: https://django-environ.readthedocs.io/en/latest/
- Debug Toolbar: https://django-debug-toolbar.readthedocs.io/en/latest/installation.html

**Celery and Redis**
- Celery with Django: https://docs.celeryq.dev/en/stable/django/first-steps-with-django.html
- Celery tasks: https://docs.celeryq.dev/en/stable/userguide/tasks.html
- Django example: https://github.com/celery/celery/tree/main/examples/django/
- TestDriven Celery: https://testdriven.io/blog/django-and-celery/
- TestDriven periodic tasks: https://testdriven.io/blog/django-celery-periodic-tasks/
- Flower: https://flower.readthedocs.io/

**Auth**
- Simple JWT: https://django-rest-framework-simplejwt.readthedocs.io/en/stable/
- Simple JWT repo: https://github.com/jazzband/djangorestframework-simplejwt

**Other**
- all-MiniLM-L6-v2: https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2
- factory_boy: https://factoryboy.readthedocs.io/
- GitHub service containers: https://docs.github.com/en/actions/using-containerized-services
- drf-spectacular: https://drf-spectacular.readthedocs.io/
