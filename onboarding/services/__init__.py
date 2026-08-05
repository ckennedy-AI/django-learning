"""Re-exports the public services, so callers import from the package path.

One module today. `task_assignment_approve` writes an `ActivityEvent` as well as
a `TaskAssignment`, but the outcome it owns is an approved task assignment, so it
belongs to the `onboarding_tasks` sub-domain. That module name is
`onboarding_tasks` rather than `tasks` to stay unambiguous against
`onboarding/tasks.py`, which is reserved for Celery tasks.
"""

from onboarding.services.onboarding_tasks import task_assignment_approve

__all__ = [
    "task_assignment_approve",
]
