"""Celery tasks, and nothing else.

Every task in here is thin on purpose: it receives an ID, calls a service, and
returns whatever that service returned. Business logic lives in the service so
it is reachable from a test, a shell, or a management command without a broker
in the picture, and so the only difference between running work in-process and
running it on a worker is which of the two calls it.

What does belong in this file is the execution policy: retries, time limits, and
which queue a task lands on. Those are properties of running the work, not of
the work, and keeping them here means the service stays callable from anywhere.
Queue routing is the one exception, configured centrally in
`CELERY_TASK_ROUTES` rather than per task, so the map of queues can be read in
one place. See `config/settings.py`.

A task runs outside the request cycle. There is no `request.user`, no
permission class, and no way to ask who triggered it. Authorization was decided
before the enqueue: `generate_skill_embedding` only ever runs because
`SkillCreateApi` let a staff caller through, or because `SkillAdmin` did. The
two beat-scheduled tasks have no human caller at all, which is its own answer:
nobody authorized them, so neither one may do anything a specific user's
permissions would have gated.

Services import their task with a `_task` suffix at module level; tasks import
their service inside the function body. That asymmetry is what breaks the
import cycle, since `onboarding.services` imports `onboarding.tasks` at import
time and the reverse would deadlock at first import.
"""

from celery import shared_task


@shared_task(
    # Both limits are raised above the project-wide 60/90 in settings, because
    # the first embedding on a cold worker child pays for loading
    # all-MiniLM-L6-v2 from disk before it encodes anything. A cold-start cost
    # is not the runaway this limit is meant to catch.
    soft_time_limit=120,
    time_limit=150,
)
def generate_skill_embedding(skill_id: int) -> dict:
    """Embeds one skill's description.

    @shared_task rather than @app.task so this module never imports the Celery
    app: the task binds to whichever app is current, which is the one
    config/__init__.py constructed at Django startup.

    The argument is an ID, not a Skill. Two distinct reasons: the row may have
    changed between enqueue and execution, so the worker should read current
    state rather than a snapshot, and CELERY_TASK_SERIALIZER is json, which
    cannot represent a model instance at all.

    Routed to the `embeddings` queue by CELERY_TASK_ROUTES, and consumed by the
    `celery-worker-embeddings` compose service at --concurrency=1. It is the only
    task whose worker child holds a sentence-transformers model in memory, so it
    is the only one whose concurrency is a memory decision.

    No retry configuration on purpose. The failure modes are a deleted row and a
    broken model load, and neither improves on a second attempt.
    """
    from onboarding.services import skill_embedding_set

    return skill_embedding_set(skill_id=skill_id)


@shared_task
def score_assessment_attempt(attempt_id: int) -> dict:
    """Scores one submitted assessment attempt.

    Idempotent, which is the reason it is safe for the broker to deliver this
    message twice. It can: a worker that is killed after starting a task, or
    that loses its Redis connection before acknowledging, leaves the message to
    be redelivered. The task itself does nothing to protect against that, and
    should not. The guarantee lives in `assessment_attempt_score`, as a
    conditional UPDATE on `scored_at` whose affected row count decides whether
    this run owns the transition. Read that docstring for why a
    check-then-write, including `get_or_create`, does not hold here.

    No retries. A failure here is a missing attempt or a bug, not a transient
    outage, and retrying it would only produce the same exception on a schedule.
    """
    from onboarding.services import assessment_attempt_score

    return assessment_attempt_score(attempt_id=attempt_id)


@shared_task(
    # smtplib.SMTPException subclasses OSError, as do socket.timeout and
    # ConnectionError, so this one entry covers "the mail server was not
    # reachable or refused us" without listing every way that happens. A
    # ValidationError or a bug in the service is deliberately not in here: those
    # do not get better on a retry, and a failure that stays visible is more
    # useful than one that is attempted six times and then lost.
    autoretry_for=(OSError,),
    # Exponential: the countdown doubles from one second per attempt, capped by
    # retry_backoff_max, so a mail server that is briefly down is retried
    # quickly and one that is properly down is retried patiently.
    retry_backoff=True,
    retry_backoff_max=600,
    # Jitter spreads the retries randomly inside the backoff window. Without it,
    # every task that failed during the same outage retries at the same instant
    # and re-creates the load that caused it.
    retry_jitter=True,
    max_retries=5,
)
def send_overdue_reminders() -> dict:
    """Emails everyone with overdue onboarding modules. Scheduled by beat.

    No arguments, and none to pass: beat publishes this on a crontab and there
    is no caller to take a parameter from. The service defaults `as_of` to today
    for the same reason, and still accepts it so a rerun for a past date is
    possible from a shell.

    The retry configuration above is only half of what makes a retry safe. A
    retry re-runs the whole batch, so the service has to be resumable, not just
    re-runnable: it logs an ActivityEvent per recipient as it goes and the
    selector excludes anyone already logged inside the reminder window. Without
    that, attempt six of a batch that fails on its last recipient would send
    every earlier one a sixth email.
    """
    from onboarding.services import overdue_reminders_send

    return overdue_reminders_send()


@shared_task
def rollup_department_progress() -> dict:
    """Snapshots per-department progress for today. Scheduled by beat, nightly.

    Idempotent by a unique constraint on (department, captured_on) rather than by
    a conditional UPDATE, because what must happen once here is the existence of
    a result row rather than a transition on an existing one. See
    `department_progress_rollup`.

    No retries, and the schedule is the reason: this runs every night, and a
    failed run is a gap of one day in a history that the next run does not
    depend on. `expires` in CELERY_BEAT_SCHEDULE matters more than a retry would,
    since a message that sat in the queue while every worker was down should be
    dropped rather than run at noon the next day.
    """
    from onboarding.services import department_progress_rollup

    return department_progress_rollup()
