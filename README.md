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

Development happens on Windows in PowerShell. Docker Compose lands in a later phase; for now
this runs directly against a virtual environment and SQLite.

1. Create and activate a virtual environment:

    ```powershell
    python -m venv .venv
    .venv\Scripts\Activate.ps1
    ```

2. Install dependencies:

    ```powershell
    pip install -r requirements.txt
    ```

3. Copy `.env.example` to `.env` and fill in real values. `.env` is gitignored and must never
   be committed:

    ```powershell
    Copy-Item .env.example .env
    ```

4. Apply migrations and create a superuser:

    ```powershell
    python manage.py migrate
    python manage.py createsuperuser
    ```

5. Run the development server:

    ```powershell
    python manage.py runserver
    ```

## Environment variables

Read via `django-environ` in `config/settings.py`.

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | Django's cryptographic signing key. Never reuse across environments. |
| `DEBUG` | Must be `False` outside local development. |
| `ALLOWED_HOSTS` | Comma-separated list of hosts Django will serve. |
| `DATABASE_URL` | Parsed by `env.db()`. SQLite for now (`sqlite:///db.sqlite3`); becomes a `postgres://` URL once Docker Compose is introduced. |
| `REDIS_URL` | Parsed by `env.cache()`. Backs the cache framework and, later, the Celery broker. |

## Project structure

```
config/         # settings, root urls, wsgi/asgi, celery app
onboarding/     # domain app: modules, assignments, tasks, skills
manage.py
requirements.txt
```

## Running tests

```powershell
python manage.py test
```
