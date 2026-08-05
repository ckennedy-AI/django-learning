from django.shortcuts import get_object_or_404

from onboarding.models import TaskAssignment


def task_assignment_get_for_manager(*, task_assignment_id: int, manager_id: int) -> TaskAssignment:
    """Scope the lookup to assignments belonging to this manager's direct reports.

    A manager may approve their own direct reports' tasks and nobody else's.
    Scoping the query itself, rather than fetching by id and checking
    afterward, means a task assignment belonging to someone else's report
    returns 404 instead of leaking that the row exists.
    """
    return get_object_or_404(
        TaskAssignment.objects.select_related("assignee"),
        id=task_assignment_id,
        assignee__manager_id=manager_id,
    )
