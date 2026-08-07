from datetime import date

from django.db import transaction
from django.utils import timezone

from onboarding.models import DepartmentProgressSnapshot
from onboarding.selectors import department_activity_report_list


def department_progress_rollup(*, captured_on: date | None = None) -> dict:
    """Writes one progress snapshot per department for a given date.

    The aggregation itself is not re-implemented here: it calls
    `department_activity_report_list`, the selector that already backs
    `DepartmentActivityReportApi`. A service calling a selector is the allowed
    direction, and the reuse is deliberate: two definitions of "completion
    percentage" that drift apart would make the nightly history disagree with the
    live report while both looked correct. The cost is inherited too, since that
    selector runs four queries per department by design. That was an explicit
    tradeoff for an occasional admin report, and it is an even easier one for a
    task running at 02:30 with nobody waiting.

    Idempotent by unique constraint, not by inspection. `update_or_create` on
    (department, captured_on) is a SELECT and then either an UPDATE or an INSERT,
    which is check-then-write and therefore racy on its own: two runs for the same
    date can both miss and both insert. What makes it safe is
    `unique_department_snapshot_per_day` on the model. With the constraint in
    place, the loser's INSERT raises IntegrityError, Django's own `get_or_create`
    catches exactly that, re-fetches the winning row, and the caller gets one row
    either way. Drop the constraint and the same code silently produces two rows
    per department per day, which is the failure this phase is about: the
    constraint is the idempotency, and the ORM call is just a convenient way to
    use it.

    Compare `assessment_attempt_score`, which uses a conditional UPDATE instead.
    That one guards a state transition on an existing row, where there is nothing
    for a constraint to be unique about. This one guards the existence of a result
    row, which is exactly what a unique constraint expresses.

    `captured_on` is an argument rather than a call to the clock inside the loop,
    so a rerun for a past date lands on that date's rows, and so a run that
    crosses midnight does not write half its snapshots under each date.
    """
    captured_on = captured_on or timezone.localdate()

    report = department_activity_report_list()

    # One transaction around the whole rollup, the opposite call from
    # `overdue_reminders_send`. Here the write is a single logical snapshot of a
    # single moment, and a half-written night is worse than no night at all:
    # there is nothing external to undo, and the retry recomputes everything from
    # scratch anyway.
    with transaction.atomic():
        for row in report:
            DepartmentProgressSnapshot.objects.update_or_create(
                department_id=row["department_id"],
                captured_on=captured_on,
                defaults={
                    "employee_count": row["employee_count"],
                    "completion_percentage": row["completion_percentage"],
                    "activity_event_count": row["activity_event_count"],
                },
            )

    return {"captured_on": captured_on.isoformat(), "departments": len(report)}
