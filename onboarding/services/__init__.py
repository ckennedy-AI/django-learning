"""Re-exports the public services, so callers import from the package path.

Five modules as of Phase 12, and three of them exist because a Celery task needs
a service to call. Placement of each, since none of the three is reached by an
endpoint and the sub-domain rule therefore falls to CLAUDE.md's tie-breakers:

`task_assignment_approve` writes an `ActivityEvent` as well as a
`TaskAssignment`, but the outcome it owns is an approved task assignment, so it
belongs to the `onboarding_tasks` sub-domain. That module name is
`onboarding_tasks` rather than `tasks` to stay unambiguous against
`onboarding/tasks.py`, which is reserved for Celery tasks.

`skill_embedding_set` is in `services/skills.py` beside `skill_create` even
though no endpoint reaches it directly: the tie-breaker is the entity that owns
the outcome, and the outcome is an embedded `Skill`. Its caller is
`onboarding/tasks.py`, which is a flat module outside the sub-domain layout, so
"goes with its caller" does not apply here.

`overdue_reminders_send` is in `services/modules.py` by the same first
tie-breaker: it sends mail and writes activity events, but what it is about is an
overdue `ModuleAssignment`. `services/modules.py` is a new module here rather
than a home for an existing endpoint's writes, since no endpoint writes a module
yet, and `selectors/modules.py` already owned the matching read.

`department_progress_rollup` is in `services/departments.py` because it writes
`DepartmentProgressSnapshot` rows. Note that it reads through
`department_activity_report_list`, the selector behind
`DepartmentActivityReportApi`: same sub-domain, one definition of the numbers,
and a service calling a selector is the allowed direction.

`assessment_attempt_create` and `assessment_attempt_score` open
`services/assessments.py`, the first content the `assessments` sub-domain has in
any layer above models. It still owns no endpoints and no selectors, which is why
there is no `views/assessments.py` or `selectors/assessments.py` to match: a
module is created when that sub-domain has content in that layer, not to keep the
layers symmetrical.
"""

from onboarding.services.assessments import assessment_attempt_create, assessment_attempt_score
from onboarding.services.departments import department_progress_rollup
from onboarding.services.modules import overdue_reminders_send
from onboarding.services.onboarding_tasks import task_assignment_approve
from onboarding.services.skills import skill_create, skill_embedding_set

__all__ = [
    "assessment_attempt_create",
    "assessment_attempt_score",
    "department_progress_rollup",
    "overdue_reminders_send",
    "skill_create",
    "skill_embedding_set",
    "task_assignment_approve",
]
