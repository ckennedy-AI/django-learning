# Celery

Background jobs for this project. Four tasks, two queues, two workers, and a
scheduler. Phase 11 got one task running end to end; Phase 12 added the rest,
the execution policy around them, and beat and Flower.

## Topology

```
POST /api/skills/            docker compose service: web
  SkillCreateApi
    skill_create()           writes the Skill row inside transaction.atomic
      COMMIT                 <-- nothing is enqueued before this point
      apply_async()          publishes to Redis db 0, routed to `embeddings`
                                     |
   (a service, no endpoint yet)      |
  assessment_attempt_create()        |
      COMMIT                         |
      apply_async()          publishes to Redis db 0, queue `default`
                                     |
  celery -A config beat              |
    publishes on a crontab   -----> Redis (broker, db 0)
                                    /                  \
                          queue `default`         queue `embeddings`
                                  |                       |
                        celery-worker            celery-worker-embeddings
                        --concurrency=2          --concurrency=1
                        score_assessment_attempt generate_skill_embedding
                        send_overdue_reminders
                        rollup_department_progress
                                  \                      /
                                   Redis (results, db 2)
                                            |
                                   celery -A config flower
                                   http://localhost:5555
```

Every arrow crosses a process boundary. Nothing shares memory, and only
committed rows are visible to a worker.

## The tasks

| Task | Trigger | Queue | Retries | Time limits | Idempotency |
|---|---|---|---|---|---|
| `generate_skill_embedding(skill_id)` | `skill_create`, on create | `embeddings` | none | 120 soft / 150 hard | recomputes and overwrites the same vector |
| `score_assessment_attempt(attempt_id)` | `assessment_attempt_create`, on submit | `default` | none | 60 / 90 (project default) | conditional `UPDATE` on `scored_at` |
| `send_overdue_reminders()` | beat, 13:00 UTC daily | `default` | `OSError`, backoff to 600s, jitter, max 5 | 60 / 90 | resumable batch, 20 hour reminder window |
| `rollup_department_progress()` | beat, 02:30 UTC daily | `default` | none | 60 / 90 | unique constraint on `(department, captured_on)` |

Only one task retries, and that is the point of the column: a retry is for a
failure that is expected to stop happening. A deleted row, a bad argument, or a
bug fails the same way on every attempt, and a task that retries it six times has
turned one loud failure into six quiet ones plus a delay.

## Idempotency, three ways

The reason a task needs to be safe to run twice is that Celery gives you
at-least-once delivery, not exactly-once. A worker that is killed mid-task, or
that loses its Redis connection before acknowledging a message, leaves that
message to be redelivered. Nothing in the broker prevents it, so the protection
belongs in the service.

**Check-then-write is the trap, and `get_or_create` is check-then-write.** It
issues a `SELECT`, and then an `INSERT` if the select found nothing. Two callers
can both reach the select, both find nothing, and both insert. The window is
small and completely real. `update_or_create` has the same shape.

**A unique constraint is what closes it, when the thing that must happen once is
a row existing.** `rollup_department_progress` uses this. With
`unique_department_snapshot_per_day` in place, the loser's `INSERT` raises
`IntegrityError`; Django's own `get_or_create` catches exactly that exception and
re-fetches the winning row, so both callers end up with one row. Delete the
constraint and the identical Python silently produces duplicates. The constraint
is the idempotency; `update_or_create` is just a convenient way to lean on it.

**A conditional UPDATE is what closes it, when the thing that must happen once is
a state transition.** `assessment_attempt_score` uses this:
`UPDATE ... WHERE scored_at IS NULL`, and then it trusts the affected row count.
The test and the write are one statement, so the database does the deciding.
Under Postgres' default READ COMMITTED, a second transaction running the same
statement blocks on the first one's row lock, re-evaluates the `WHERE` clause
after that commit, matches nothing, and reports zero rows. The caller that got 1
owns the transition and writes the activity event; the caller that got 0 must
not. There is nothing here for a unique constraint to be unique about, which is
why the mechanism differs from the rollup's.

**Resumability is the third kind, and it is what a batch task needs.**
`send_overdue_reminders` sends email, and an SMTP conversation cannot be rolled
back. So the loop is deliberately *not* wrapped in one transaction: each reminder
is logged as an `ActivityEvent` immediately after its send, and the selector
excludes anyone logged inside the reminder window. A crash halfway through leaves
the earlier reminders logged, and the retry picks up only what is left. One
transaction around the batch would roll those log rows back and email everybody
again on attempt two.

That leaves one honest gap: if the mail is accepted and the process dies before
the event row commits, that person gets a second email on the retry. Closing it
would require the send and the log to be one atomic operation, which they cannot
be. Sending a duplicate reminder is the cheaper failure than silently not
sending one, so the order is send first, log second.

## Time limits

Two limits, and the difference is the whole reason there are two.

- `soft_time_limit` raises `SoftTimeLimitExceeded` **inside** the task, at a
  Python bytecode boundary. The task can catch it, clean up, and exit on its own
  terms.
- `time_limit` is the hard kill. The worker sends `SIGKILL` to the child process.
  No exception is raised, no `finally` block runs, and any open transaction is
  rolled back by Postgres when the connection drops.

The gap between them is the grace period. Project defaults are 60 and 90 seconds,
in `config/settings.py`. `generate_skill_embedding` raises its own to 120 and 150,
because a cold worker child loads `all-MiniLM-L6-v2` from disk before it encodes
anything, and a cold start is not the runaway the limit is there to catch.

## Queues

One queue per resource profile, not one per task. Everything goes to `default`
unless `CELERY_TASK_ROUTES` says otherwise, and exactly one task is routed away.

`generate_skill_embedding` is the only task whose worker child holds a
sentence-transformers model in RAM, which makes its concurrency a memory decision
rather than a throughput one. Putting it on its own queue with its own worker at
`--concurrency=1` means the other three do not have to share that constraint, and
the isolation runs both ways: a backlog of embeddings cannot delay the nightly
rollup, and a burst of reminders cannot queue behind a model load.

Two consequences worth knowing:

- **A route is keyed by task name**, which for a `@shared_task` is its module
  path plus function name. Rename the function or move `tasks.py` and the route
  silently stops matching, so the task lands on `default` and a worker that has
  never loaded the model runs it. `TaskExecutionPolicyTests` pins the name for
  exactly this reason.
- **A queue with no worker consumes nothing.** Messages accumulate in Redis and
  nothing errors. `docker compose ps` showing the embeddings worker as absent is
  the only symptom.

## Beat

`celery-beat` publishes messages on a schedule and executes nothing. Exactly one
beat process may run: two schedulers reading the same schedule publish the same
task twice.

The schedule lives in `CELERY_BEAT_SCHEDULE` in `config/settings.py` as code, and
`PersistentScheduler` keeps each entry's `last_run_at` in a shelve file on the
`beat-schedule` volume, at `/var/lib/celery/celerybeat-schedule`. The volume is
what makes a restart resume rather than start over, and keeping the file off the
`/app` bind mount is what keeps it out of the repository.

`django-celery-beat` is the alternative. It stores the schedule in Postgres and
makes it editable from the admin, at the cost of a dependency and its own
migrations. Not used here, because this schedule is code that should change
through a commit rather than through a form.

**Beat does not backfill.** If the scheduler was down when an entry was due, that
run is skipped; the next run is computed from the crontab. There is no catch-up
queue and no record that a firing was missed.

**The opposite case is the dangerous one.** If beat is up and the *workers* are
down, beat keeps publishing and the messages pile up in Redis, then all run at
once when a worker returns. That is what `expires` in each schedule entry is for:
the broker drops a message that is no longer worth running. Six hours here, on
the reasoning that yesterday's overdue reminder is noise and yesterday's rollup
is recomputed by tonight's run anyway.

## Flower

`http://localhost:5555`. Flower watches the broker and the task event stream, so
it can show queued, running, and finished tasks without being wired into the
application at all. It needs two settings that are off by default, which is why
the worker banner used to read `task events: OFF`:

- `CELERY_WORKER_SEND_TASK_EVENTS` makes a worker announce started, succeeded,
  and failed.
- `CELERY_TASK_SEND_SENT_EVENT` makes the *publishing* process announce the
  enqueue, which is what lets Flower show a task no worker has picked up yet.

Events cost a message each, which is why they are opt-in rather than on.

Two things to know about access. The UI is unauthenticated here, which is fine on
a laptop and unacceptable anywhere else: anyone who can reach the port can read
every task argument and revoke tasks. The JSON API under `/api/` is separately
gated and returns 401 by default in Flower 2.x, which is deliberate on Flower's
part; `--unauthenticated_api` opens it if a script needs it, and real
authentication is the better answer.

The Celery CLI answers the same questions without a browser, and over the broker
rather than by importing anything:

```powershell
docker compose exec celery-worker celery -A config inspect registered
docker compose exec celery-worker celery -A config inspect active
docker compose exec celery-worker celery -A config inspect active_queues
docker compose exec celery-worker celery -A config inspect scheduled
```

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
| `config/settings.py` | every `CELERY_*` setting: connections, routes, limits, the beat schedule |
| `onboarding/tasks.py` | task definitions, thin, plus per-task retry and time limit policy |
| `onboarding/services/skills.py` | `skill_create` (enqueues), `skill_embedding_set` (the work) |
| `onboarding/services/assessments.py` | `assessment_attempt_create` (enqueues), `assessment_attempt_score` (the work) |
| `onboarding/services/modules.py` | `overdue_reminders_send` |
| `onboarding/services/departments.py` | `department_progress_rollup` |
| `onboarding/selectors/modules.py` | `module_assignment_overdue_user_list`, the reminder's read |

## Commands

```powershell
docker compose up -d celery-worker celery-worker-embeddings celery-beat flower
docker compose logs -f celery-worker
docker compose logs -f celery-worker-embeddings
docker compose logs -f celery-beat

# After changing task or service code. Neither worker reloads on its own, and
# beat has to be restarted too if the schedule changed.
docker compose restart celery-worker celery-worker-embeddings celery-beat

# Create a skill, then poll the result backend until its task finishes.
docker compose exec web python manage.py inspect_task_result
docker compose exec web python manage.py inspect_task_result --keep

# Run a scheduled task now rather than waiting for its crontab.
docker compose exec web python manage.py shell -c "from onboarding.tasks import send_overdue_reminders; print(send_overdue_reminders.delay().get(timeout=120))"
docker compose exec web python manage.py shell -c "from onboarding.tasks import rollup_department_progress; print(rollup_department_progress.delay().get(timeout=120))"
```

The workers do not reload on code changes. Celery's watchdog-based reloader is
documented as unsuitable for anything but experimentation, so a code change means
a restart. Forgetting produces the most confusing class of failure available
here: `web` runs new code, the worker runs old code, and the two disagree about
what a task does.

## Things that bite

**A task enqueued inside `transaction.atomic` can run before the row exists.**
The worker is a separate process with its own connection and only sees committed
data. Enqueue with `transaction.on_commit`. Both enqueueing services do, and it
is worth breaking on purpose once: swap it for a bare `.delay()` and watch the
worker fail with `DoesNotExist`, intermittently, depending on who wins the race.

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
written to Postgres by the service, as the embedding and the snapshots are.

**A task's return value has to be JSON.** `CELERY_RESULT_SERIALIZER = "json"`, so
every task here returns a small dict of primitives. A `date` is not JSON either,
which is why the two scheduled services return `.isoformat()` strings.

**The embedding worker holds its own copy of the model.** The prefork pool forks
one child per concurrency slot, and each child that runs an embedding task loads
`all-MiniLM-L6-v2` into its own memory. `--concurrency=1` on that service is a
memory decision. The first task after a restart is slow because the model is
being loaded; the `hf-cache` volume is mounted into that worker so it is not
being re-downloaded. It is deliberately not mounted into `celery-worker`, which
has no task that loads a model.

**A worker warns that it is running as root.** Development only, from running as
the image's default user under a bind mount. It is a warning, not a failure.

**Flower's inspect calls fail during startup.** If Flower comes up before the
workers do, its log carries a handful of `Inspect method ... failed` warnings and
then settles. They mean no worker was answering yet, not that Flower is
misconfigured.

## Authorization

A task has no `request.user`, no permission class, and no way to ask who
triggered it. Authorization was decided before the enqueue:
`generate_skill_embedding` only ever runs because `SkillCreateApi` let a staff
caller through, or because `SkillAdmin` did. When reading a worker log, "who was
allowed to cause this" is not a question the log can answer.

The two beat-scheduled tasks make the point from the other side. Nobody triggered
them, so there is no caller whose permissions could be checked, and neither one
may do anything that a specific user's permissions would have gated. That is a
design constraint on what a scheduled task is allowed to be, not a gap to fill in
later.

## Known gaps

- `score_assessment_attempt` has no endpoint triggering it yet. The
  `assessments` sub-domain owns no endpoints, so `assessment_attempt_create` is
  reached from tests and the shell. It will not need changing when an
  `AssessmentAttemptCreateApi` arrives.
- Passing an assessment does not complete the related module assignment. That
  write would also have to invalidate the user's dashboard cache, which CLAUDE.md
  parks with the endpoint that will own module completion.
- Editing a skill description in the admin does not re-embed it, so the vector
  goes stale. `SkillAdmin.save_model` documents this at the point where it would
  be fixed.
- Nothing reads `DepartmentProgressSnapshot` yet. Normal for a rollup: the
  history has to accumulate before a trend report can exist.
