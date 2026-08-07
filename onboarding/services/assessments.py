import uuid

from django.db import transaction
from django.utils import timezone

from onboarding.models import ActivityEvent, AssessmentAttempt
from onboarding.tasks import score_assessment_attempt as score_assessment_attempt_task

ATTEMPT_SCORED_EVENT_TYPE = "assessment_scored"


def assessment_attempt_create(
    *, user_id: int, assessment_id: int, score: int
) -> tuple[AssessmentAttempt, str]:
    """Records a submitted attempt and hands the scoring off to a worker.

    Deliberately shaped like `skill_create`: write the row, pre-generate a task
    id so the caller can name the task it triggered, enqueue on commit, return.
    Repeating that shape is the point. It is the project's answer to "a request
    should return before the slow or failure-prone part happens", and a second
    example is what turns it from a one-off into a pattern.

    There is no endpoint calling this yet, which is a real gap and not an
    oversight. Phase 12's job is the task layer, and `assessments` still owns no
    endpoints in CLAUDE.md's sub-domain table. The service exists because the
    task table says this task is triggered "on attempt submit", and a trigger
    that lives nowhere is a trigger that is never exercised: this is what the
    tests and the shell call, and what an `AssessmentAttemptCreateApi` will call
    unchanged when the phase that owns it arrives.

    full_clean before save costs a few queries, and buys two things: the
    existing score-range check constraint is validated in Python, so a bad score
    is a ValidationError that `api/exception_handlers.py` turns into a 400 with
    the field name, rather than an IntegrityError and a 500. It also validates
    that the two foreign keys point at rows that exist.
    """
    with transaction.atomic():
        attempt = AssessmentAttempt(user_id=user_id, assessment_id=assessment_id, score=score)
        attempt.full_clean()
        attempt.save()

        scoring_task_id = str(uuid.uuid4())

        # on_commit, not a bare .delay(). The worker has its own connection and
        # sees only committed rows, so an enqueue inside the transaction can win
        # the race and score an attempt that does not exist yet.
        transaction.on_commit(
            lambda: score_assessment_attempt_task.apply_async(
                args=[attempt.id], task_id=scoring_task_id
            )
        )

    return attempt, scoring_task_id


def assessment_attempt_score(*, attempt_id: int) -> dict:
    """Scores one attempt exactly once, however many times it is called.

    This is the phase's idempotency exercise, and the mechanism is a
    compare-and-swap rather than a check-then-write.

    Why not check-then-write. The obvious version reads the attempt, sees
    `scored_at is None`, and then writes. Two workers running this concurrently,
    which is what happens when a message is redelivered after a worker dies
    mid-task, both read None, both write, and both create an ActivityEvent. The
    window between the read and the write is small and entirely real.
    `get_or_create` has the same shape and therefore the same problem: it is a
    SELECT followed by an INSERT, and nothing but a database constraint stops
    two callers from both reaching the INSERT.

    Why the conditional UPDATE closes it. `UPDATE ... WHERE scored_at IS NULL`
    makes the test and the write one statement, so the database does the
    deciding. Under Postgres' default READ COMMITTED, a second transaction
    running the same statement blocks on the row lock the first one holds, and
    when that commits, re-evaluates the WHERE clause against the new committed
    state, matches nothing, and reports zero rows affected. That returned count
    is the whole gate: the caller that got 1 owns the transition and writes the
    activity event, the caller that got 0 did not and must not.

    The other correct answer, and why it is not used here. A unique constraint
    plus a caught IntegrityError also works, and it is what
    `rollup_department_progress` uses. The difference is what the operation is:
    a rollup produces a row per (department, date), so uniqueness of the *result*
    is expressible as a constraint. Scoring produces a state transition on an
    existing row, so the thing that must happen once is an UPDATE, and a
    constraint has nothing to be unique about. Match the mechanism to the shape
    of the write.

    The event write is inside the same transaction as the swap, so a failure
    between them rolls the swap back and the next delivery scores it cleanly.
    """
    with transaction.atomic():
        attempt = AssessmentAttempt.objects.select_related("assessment").get(id=attempt_id)

        passed = attempt.score >= attempt.assessment.passing_score
        scored_at = timezone.now()

        rows_scored = AssessmentAttempt.objects.filter(
            id=attempt_id, scored_at__isnull=True
        ).update(passed=passed, scored_at=scored_at)

        if rows_scored == 0:
            # Somebody else won. The instance above was read before that commit
            # landed, so it still says None; re-read the two columns rather than
            # reporting a stale answer. One extra query, only on the duplicate
            # path.
            attempt.refresh_from_db(fields=["passed", "scored_at"])
            return {"attempt_id": attempt_id, "passed": attempt.passed, "scored": False}

        ActivityEvent.objects.create(
            user_id=attempt.user_id,
            event_type=ATTEMPT_SCORED_EVENT_TYPE,
            occurred_at=scored_at,
            metadata={
                "attempt_id": attempt.id,
                "assessment_id": attempt.assessment_id,
                "score": attempt.score,
                "passed": passed,
            },
        )

    # Passing does not complete the module assignment here, and that is a
    # boundary rather than a missing line. Completing an assignment changes what
    # MyDashboardApi returns, so it also has to invalidate that user's dashboard
    # cache, and CLAUDE.md parks that invalidation with the endpoint that will
    # own module completion. Doing half of it from a worker would leave a cached
    # dashboard disagreeing with the database.
    return {"attempt_id": attempt_id, "passed": passed, "scored": True}
