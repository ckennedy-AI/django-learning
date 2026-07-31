# Employee Onboarding Platform

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

2. Build the images and start the three services. The first build downloads PyTorch and takes a
   while; later starts are fast:

    ```powershell
    docker compose up --build
    ```

3. In a second terminal, apply migrations and create a superuser:

    ```powershell
    docker compose exec web python manage.py migrate
    docker compose exec web python manage.py createsuperuser
    ```

The app is served at http://localhost:8000, and the admin at http://localhost:8000/admin/.

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
| `DEBUG` | Must be `False` outside local development. |
| `ALLOWED_HOSTS` | Comma-separated list of hosts Django will serve. |
| `DATABASE_URL` | Parsed by `env.db()` into the `DATABASES` dict. Host is the `db` service. |
| `REDIS_URL` | Parsed by `env.cache()` into `CACHES`. Redis database 1. |
| `CELERY_BROKER_URL` | Celery broker. Redis database 0, kept separate from the cache on purpose. |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | Consumed by the `db` service to initialize the cluster. Must agree with `DATABASE_URL`. |

## Project structure

```
config/         # settings, root urls, wsgi/asgi, celery app
onboarding/     # domain app: modules, assignments, tasks, skills
docs/           # docker.md and other operational notes
pyproject.toml  # Ruff lint and format configuration
manage.py
requirements.txt
```

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
