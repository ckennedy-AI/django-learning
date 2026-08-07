"""Re-exports the public services, so callers import from the package path.

Two modules today.

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
"""

from onboarding.services.onboarding_tasks import task_assignment_approve
from onboarding.services.skills import skill_create, skill_embedding_set

__all__ = [
    "skill_create",
    "skill_embedding_set",
    "task_assignment_approve",
]
