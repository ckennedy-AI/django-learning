# Docker development environment

Three services, defined in `docker-compose.yml`: `web` (the Django app), `db` (Postgres), `redis`. The `db` service must stay on `pgvector/pgvector:pg17`, never the stock `postgres` image, because the vector extension binary only ships in that image.

## Starting the environment

```powershell
docker compose up
```

Add `--build` whenever `requirements.txt` or the `Dockerfile` changed, so the `web` image gets rebuilt:

```powershell
docker compose up --build
```

Add `-d` to run in the background instead of holding the terminal:

```powershell
docker compose up -d
```

`web` will not actually start serving requests until both `db` and `redis` report healthy. That wait is handled by the `depends_on: condition: service_healthy` entries in the compose file, using `pg_isready` and `redis-cli ping` under the hood, so no manual retry loop is needed here.

`depends_on` on its own would only wait for each container to have been *started*, which for Postgres means the process exists, not that it is accepting connections. On a fresh volume the image also runs `initdb` against a temporary server first, so the health check targets `127.0.0.1` rather than the unix socket: the temporary server does not listen on TCP, which keeps the check failing until the real server is actually reachable the same way Django reaches it.

## Stopping the environment

```powershell
docker compose down
```

This stops and removes the containers but keeps the two named volumes (`postgres-data`, `hf-cache`), so your database rows and the downloaded embedding model survive.

```powershell
docker compose down -v
```

Adding `-v` also deletes those named volumes. This wipes the entire database and forces a re-download of the embedding model on next start. Only run this intentionally.

## Running Django management commands

Every `manage.py` command runs inside the `web` container, never on the host directly, since Python and all dependencies live there:

```powershell
docker compose exec web python manage.py migrate
docker compose exec web python manage.py makemigrations
docker compose exec web python manage.py createsuperuser
docker compose exec web python manage.py shell
docker compose exec web python manage.py test
docker compose exec web python manage.py seed_data --events 100000
```

## Connecting to Postgres directly

```powershell
docker compose exec db psql -U postgres -d onboarding
```

To confirm the pgvector extension is actually available in the running database:

```powershell
docker compose exec db psql -U postgres -d onboarding -c "SELECT * FROM pg_available_extensions WHERE name = 'vector';"
```

This should return exactly one row. If it returns nothing, the `db` image is wrong, not the extension migration.

## Watching logs

```powershell
docker compose logs -f web
docker compose logs -f db
docker compose logs -f celery-worker
```

The last one only applies once the Celery worker service is added in a later phase.

## Rebuilding after a dependency change

Any time `requirements.txt` gains, removes, or updates a package, rebuild the `web` image:

```powershell
docker compose up --build
```

Because the Dockerfile copies `requirements.txt` and runs `pip install` before copying the rest of the source, Docker reuses the cached dependency layer whenever `requirements.txt` itself is unchanged, so a source-only rebuild stays fast.

## Resetting the database before the custom user model lands

Read this before starting phase 4. It is the one place where the phase 3 instructions and the
phase 4 instructions can collide.

`AUTH_USER_MODEL` has to be set before the first `migrate` that creates the auth tables. If
`migrate` has already run against the default `auth.User`, then swapping in a custom user model
fails, because `django.contrib.admin` and `django.contrib.auth` migrations are already recorded
as applied against a user table that is about to be replaced. Django reports this as an
`InconsistentMigrationHistory` error or as a lazy-reference `ValueError` on `admin.LogEntry.user`.

Check whether `migrate` has already run:

```powershell
docker compose exec db psql -U postgres -d onboarding -c "\dt"
```

If that lists `auth_user`, `django_admin_log`, and friends, drop the database volume and start
clean before writing the custom user model. There is no data worth keeping yet:

```powershell
docker compose down -v
docker compose up
```

Then define the custom `User` model, set `AUTH_USER_MODEL`, and only then run the first
`makemigrations` and `migrate`. If the table list came back empty, no reset is needed.

## Confirming data survives a restart

```powershell
docker compose down
docker compose up
```

Then check that previously created rows are still present, for example through `manage.py shell` or the admin. If they are gone, something is writing to the container's own filesystem instead of the named volume, and the volume mount in `docker-compose.yml` needs a second look.
