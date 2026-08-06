# Celery

Background jobs for this project. One task exists today,
`generate_skill_embedding`, added in Phase 11 to move the slow part of creating a
skill out of the request cycle. Phase 12 adds the rest.

## Topology

```
POST /api/skills/            docker compose service: web
  SkillCreateApi
    skill_create()           writes the Skill row inside transaction.atomic
      COMMIT                 <-- nothing is enqueued before this point
      apply_async()          publishes a message to Redis db 0
                                     |
                              Redis (broker, db 0)
                                     |
  celery -A config worker    docker compose service: celery-worker
    generate_skill_embedding(skill_id)
      skill_embedding_set()  loads all-MiniLM-L6-v2, UPDATEs the vector
      return {...}           stored in Redis db 2 for CELERY_RESULT_EXPIRES
```

Two processes, two database connections, no shared memory.

## Redis database numbers

One Redis container, three logical databases, kept separate on purpose:

| Database | Used for | Setting |
|---|---|---|
| 0 | Celery broker, the message queue | `CELERY_BROKER_URL` |
| 1 | Django cache, including the dashboard payloads | `REDIS_URL` |
| 2 | Celery result backend | `CELERY_RESULT_BACKEND` |

A queue purge or a `FLUSHDB` against the broker must not be able to drop cached
dashboards, and result values must not be able to evict them under memory
pressure. Sharing a number costs nothing until the day it costs a confusing
outage.

## Where the pieces live

| File | Holds |
|---|---|
| `config/celery.py` | the app, settings namespace, `autodiscover_tasks()` |
| `config/__init__.py` | the import that constructs the app at Django startup |
| `config/settings.py` | every `CELERY_*` setting, read from the environment |
| `onboarding/tasks.py` | task definitions, thin, no business logic |
| `onboarding/services/skills.py` | `skill_create` (enqueues), `skill_embedding_set` (the work) |

## Commands

```powershell
docker compose up -d celery-worker
docker compose logs -f celery-worker
docker compose restart celery-worker      # after changing task or service code

# Create a skill, then poll the result backend until its task finishes.
docker compose exec web python manage.py inspect_task_result
docker compose exec web python manage.py inspect_task_result --keep

# Ask the worker what it has registered, over the broker rather than by import.
docker compose exec celery-worker celery -A config inspect registered
docker compose exec celery-worker celery -A config inspect active
```

The worker does not reload on code changes. Celery's watchdog-based reloader is
documented as unsuitable for anything but experimentation, so a code change means
`docker compose restart celery-worker`. Forgetting produces the most confusing
class of failure available here: `web` runs new code, the worker runs old code,
and the two disagree about what a task does.

## Things that bite

**A task enqueued inside `transaction.atomic` can run before the row exists.**
The worker is a separate process with its own connection and only sees committed
data. Enqueue with `transaction.on_commit`. This is the single most important
line in `skill_create`, and it is worth breaking on purpose once: swap it for a
bare `.delay()` and watch the worker fail with `Skill.DoesNotExist`,
intermittently, depending on who wins the race.

**`django.test.TestCase` rolls back, so `on_commit` never fires.** Any test that
covers an enqueue needs `captureOnCommitCallbacks(execute=True)`. Without it the
test passes for the wrong reason: it proves nothing was enqueued.

**Arguments are IDs, never model instances.** `CELERY_TASK_SERIALIZER = "json"`
enforces it, which is why it is pinned rather than left at the default. Beyond
serialization, an instance is a snapshot: the row can change between enqueue and
execution, and the worker should read current state.

**`PENDING` does not mean queued.** It means no state is stored under that task
id, which also covers "this id was never a task at all". `STARTED` only appears
because `CELERY_TASK_TRACK_STARTED` is on.

**Results expire.** `CELERY_RESULT_EXPIRES` is one hour. The result backend is a
debugging and polling aid, not a data store. Anything that must persist gets
written to Postgres by the service, as the embedding is.

**The worker holds its own copy of the embedding model.** The prefork pool forks
one child per concurrency slot, and each child that runs an embedding task loads
`all-MiniLM-L6-v2` into its own memory. `--concurrency=2` is a memory decision.
The first task after a restart is slow because the model is being loaded; the
`hf-cache` volume is mounted into the worker so it is not being re-downloaded.

**The worker warns that it is running as root.** Development only, from running
as the image's default user under a bind mount. It is a warning, not a failure.

## Authorization

A task has no `request.user`, no permission class, and no way to ask who
triggered it. Authorization was decided before the enqueue:
`generate_skill_embedding` only ever runs because `SkillCreateApi` let a staff
caller through, or because `SkillAdmin` did. When reading a worker log, "who was
allowed to cause this" is not a question the log can answer.

## Not built yet

Phase 12: `celery-beat` and `flower` compose services, `send_overdue_reminders`
with retries and backoff, `score_assessment_attempt` made idempotent,
`rollup_department_progress` on a schedule, task time limits, and one task routed
to a dedicated queue. Flower also needs `CELERY_WORKER_SEND_TASK_EVENTS`, which
is why the worker banner currently reports `task events: OFF`.
