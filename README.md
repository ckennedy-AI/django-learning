# Employee Onboarding Platform

[![CI](https://github.com/ckennedy-AI/django-learning/actions/workflows/ci.yml/badge.svg?branch=dev)](https://github.com/ckennedy-AI/django-learning/actions/workflows/ci.yml)

Backend-only Django project: onboarding modules with assessments, manager-approved onboarding
tasks, a company directory, and a skills directory searchable by meaning. Built as a learning
project (see `django-learning-roadmap.md`) ahead of production work on RigAgent. Architecture
conventions live in `CLAUDE.md` and `django-styleguide.md`; read those before changing code.

## Stack

Django 6.0, Django REST Framework, PostgreSQL 17 with pgvector, Redis, Celery, Docker Compose.
See `CLAUDE.md` for the full breakdown and the architectural rules (plain `APIView` only,
selectors for reads, services for writes).

## Setup

Development happens on Windows in PowerShell. The application, PostgreSQL, and Redis all run in
Docker Compose, and every `manage.py` command runs inside the `web` container. `docs/docker.md`
is the full command reference.

1. Copy `.env.example` to `.env` and adjust if needed. `.env` is gitignored and must never be
   committed. The defaults work as-is for local development:

    ```powershell
    Copy-Item .env.example .env
    ```

2. Build the images and start the seven services (`web`, `celery-worker`,
   `celery-worker-embeddings`, `celery-beat`, `flower`, `db`, `redis`). The first
   build downloads PyTorch and takes a while; later starts are fast:

    ```powershell
    docker compose up --build
    ```

3. In a second terminal, apply migrations and create a superuser:

    ```powershell
    docker compose exec web python manage.py migrate
    docker compose exec web python manage.py createsuperuser
    ```

4. Optional, but needed before any of the benchmark commands mean anything.
   `seed_data` fills the directory, the module catalogue, and the activity feed.
   The event count is the expensive part, and the pagination and index work was
   measured against 100,000 rows:

    ```powershell
    docker compose exec web python manage.py seed_data --events 100000
    ```

The app is served at http://localhost:8000, and the admin at http://localhost:8000/admin/.
Celery monitoring is at http://localhost:5555, unauthenticated and therefore local only.

### Calling the API

Every endpoint requires a JWT. `IsAuthenticated` is the project-wide default in
`REST_FRAMEWORK`, so an unauthenticated request gets 401 rather than an anonymous
response, and there is no endpoint that opts out. Trade the superuser credentials for a
token pair, then send the access token as a bearer token:

```powershell
$tokens = Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/token/ `
    -ContentType application/json `
    -Body '{"username": "your-superuser", "password": "your-password"}'

Invoke-RestMethod -Uri http://localhost:8000/api/dashboard/ `
    -Headers @{ Authorization = "Bearer $($tokens.access)" }
```

Access tokens last 15 minutes and refresh tokens last a day, and refresh tokens rotate,
so `POST /api/token/refresh/` returns a new pair and blacklists the one it replaced.
`docs/endpoints.md` is the full endpoint reference: method, path, parameters, who may
call it, and what each one costs in queries.

Background jobs run in two workers, one per queue: `celery-worker` takes everything except the
embedding task, which `celery-worker-embeddings` takes on its own queue because it is the only task
that loads a machine learning model into memory. `celery-beat` publishes the two scheduled tasks and
runs nothing itself. None of the three reloads on code changes, so restart them after touching a
task, a service a task calls, or the beat schedule. `docs/celery.md` covers the topology, the Redis
database split, why the queues are separated, how each task is made safe to run twice, and how to
watch a task run end to end.

```powershell
docker compose logs -f celery-worker
docker compose restart celery-worker celery-worker-embeddings celery-beat
```

### About the host virtual environment

A host `.venv` is useful for editor autocompletion and for reading library source, and
`requirements.txt` installs into it fine:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

It cannot run the project, though. `DATABASE_URL` and `REDIS_URL` point at the Compose service
names `db` and `redis`, which do not resolve on the host, so `python manage.py runserver` outside
the container fails to connect. Treat the host environment as tooling only.

## Environment variables

Read via `django-environ` in `config/settings.py`.

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | Django's cryptographic signing key. Never reuse across environments. |
| `JWT_SIGNING_KEY` | Simple JWT's own signing key, read into `SIMPLE_JWT["SIGNING_KEY"]`. Deliberately not `SECRET_KEY`: rotating this invalidates every outstanding access and refresh token without touching password reset links, signed cookies, or anything else derived from `SECRET_KEY`. |
| `DEBUG` | Must be `False` outside local development. |
| `ALLOWED_HOSTS` | Comma-separated list of hosts Django will serve. |
| `DATABASE_URL` | Parsed by `env.db()` into the `DATABASES` dict. Host is the `db` service. |
| `REDIS_URL` | Parsed by `env.cache()` into `CACHES`. Redis database 1. |
| `CELERY_BROKER_URL` | Celery broker. Redis database 0, kept separate from the cache on purpose. |
| `CELERY_RESULT_BACKEND` | Celery result backend. Redis database 2. See `docs/celery.md`. |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | Consumed by the `db` service to initialize the cluster. Must agree with `DATABASE_URL`. |

There is no `HF_TOKEN`, and adding one back is a mistake worth naming. `all-MiniLM-L6-v2`
is a public, ungated model that downloads anonymously, but `huggingface_hub` reads
`HF_TOKEN` out of the environment on its own, without this project asking it to. Setting
it to a placeholder or a stale value therefore sends a bearer token on a request that
would have succeeded without one. The variable that does matter is `HF_HOME`, set in the
Dockerfile rather than in `.env`, which points the download cache at the `hf-cache`
volume.

## Project structure

```
config/           # settings, root urls, wsgi/asgi, celery app
api/              # framework glue with no domain knowledge: the pagination
                  #   helper, the single DRF exception handler, inline_serializer
core/             # ApplicationError, the exception services raise
onboarding/       # the domain app, one package per layer
  models/         #   thirteen models, one module per sub-domain
  views/          #   plain APIView classes, <Entity><Action>Api
  selectors/      #   reads
  services/       #   writes and business logic
  tests/          #   by layer first, sub-domain second
  tasks.py        #   Celery tasks only, thin
  permissions.py
  urls.py
  embeddings.py
docs/             # docker.md, celery.md, testing.md, ci.md,
                  #   endpoints.md, request-cycle.md
.github/
  workflows/
    ci.yml        # lint, test, build, stub deploy
pyproject.toml    # Ruff lint and format configuration
manage.py
requirements.txt
```

`api/` and `core/` are outside `onboarding/` on purpose. Nothing in either knows what an
onboarding module is, and a second app added later would import both unchanged, which is
the test for whether something belongs in an app or beside it. `CLAUDE.md` has the full
tree, including which layers are packages and why.

## Linting

Ruff handles both linting and formatting. Configuration is in `pyproject.toml`.

```powershell
docker compose exec web ruff check .
docker compose exec web ruff format .
```

## Running tests

```powershell
docker compose exec web python manage.py test
```

The suite needs no Redis and no worker: `TESTING` in `config/settings.py` swaps the cache
to `LocMemCache` and runs Celery tasks eagerly. `docs/testing.md` covers the layout, when
to reach for a factory versus the shared `EndpointFixtures`, the three different things
"testing a Celery task" means here, and why a service wrapped in `transaction.atomic`
reports two extra queries under `assertNumQueries`.

## Where the rest of the documentation lives

| File | Covers |
|---|---|
| `docs/endpoints.md` | every endpoint: method, path, parameters, who may call it, expected volume, query count |
| `docs/request-cycle.md` | one real request traced end to end, from URL resolution to response, and what the write path adds |
| `docs/docker.md` | the seven services, the volumes, and the container command reference |
| `docs/celery.md` | worker topology, the Redis database split, the task table, and the failure modes |
| `docs/testing.md` | test layout by layer, fixtures, and query-count auditing |
| `docs/ci.md` | the CI pipeline, the parts configured outside the repo, and how to read a red run |
| `CLAUDE.md` | the architectural spec, written for Claude Code rather than for a human reader |
| `django-styleguide.md` | HackSoft's styleguide, the authority `CLAUDE.md` defers to |

## CI

`.github/workflows/ci.yml` runs four jobs, three of them in parallel because they answer
independent questions: `lint` runs `ruff check` and `ruff format --check`, `test` runs the
migrations and the suite against real service containers, `build` proves the image still builds
(which `test` cannot, since it installs `requirements.txt` straight onto the runner and never reads
the Dockerfile), and `deploy` is a stub that fans in behind the other three, fires only on a push to
`dev`, and pauses for approval on the `staging` environment. Postgres runs on
`pgvector/pgvector:pg17` rather than the stock image, which ships no vector extension binary and so
cannot run the `enable_pgvector` migration. A Redis service container is present, but the suite
never connects to it: `TESTING` in `config/settings.py` swaps the cache to `LocMemCache` and turns
on eager Celery, so Redis is there because `REDIS_URL` must still parse at import time and because
the wiring should already exist the day that stops being true. Merging into `dev` requires `lint`,
`test` and `build` to pass, but not `deploy`, which never reports on a pull request and would
therefore block every merge waiting on a check that cannot arrive.

`docs/ci.md` covers the operational half: the parts of CI that are repository settings
rather than files in the repo, how to reproduce a CI failure locally, and the failure
modes worth recognizing on sight.
