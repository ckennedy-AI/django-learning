"""The cross-domain dashboard read.

`dashboard` is the one sub-domain with no model of its own: it reads
`ModuleAssignment` and `TaskAssignment` and owns neither. That is why these
functions live here rather than in `selectors/users.py` despite their
`user_dashboard_` prefix, and it is the same reasoning that puts `MyDashboardApi`
in `views/dashboard.py`.
"""

from datetime import date

from django.core.cache import cache
from django.db.models import F

from onboarding.models import ModuleAssignment, TaskAssignment

_DASHBOARD_CACHE_TTL = 300


def _dashboard_cache_key(*, user_id: int) -> str:
    return f"onboarding:user_dashboard:{user_id}"


def user_dashboard_get(*, user_id: int) -> dict:
    """The current user's assigned modules, pending tasks, and completion rate.

    High traffic, hit on every dashboard page load, so this is cached in
    Redis and shaped with .values() rather than full model instances, to
    keep it to the minimum two queries on a cache miss and zero on a hit.
    Invalidated explicitly by user_dashboard_cache_invalidate on task
    approval. Nothing yet calls it on module completion, since no endpoint
    changes ModuleAssignment.status, but the same call belongs there once
    one exists.
    """
    cache_key = _dashboard_cache_key(user_id=user_id)
    cached = cache.get(cache_key)

    if cached is not None:
        return cached

    today = date.today()

    module_assignments = list(
        ModuleAssignment.objects.filter(user_id=user_id).values(
            "id", "status", "due_date", "completed_at", module_title=F("module__title")
        )
    )

    for assignment in module_assignments:
        assignment["is_overdue"] = (
            assignment["completed_at"] is None and today > assignment["due_date"]
        )

    total = len(module_assignments)
    completed = sum(
        1 for a in module_assignments if a["status"] == ModuleAssignment.Status.COMPLETED
    )
    completion_percentage = round(completed / total * 100, 1) if total else 0.0

    pending_tasks = list(
        TaskAssignment.objects.filter(assignee_id=user_id)
        .exclude(status=TaskAssignment.Status.APPROVED)
        .values("id", "status", task_title=F("task__title"))
    )

    dashboard = {
        "module_assignments": module_assignments,
        "pending_tasks": pending_tasks,
        "completion_percentage": completion_percentage,
    }

    cache.set(cache_key, dashboard, timeout=_DASHBOARD_CACHE_TTL)

    return dashboard


def user_dashboard_cache_invalidate(*, user_id: int) -> None:
    cache.delete(_dashboard_cache_key(user_id=user_id))
