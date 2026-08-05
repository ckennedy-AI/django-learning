from django.db import transaction
from django.utils import timezone

from core.exceptions import ApplicationError
from onboarding.models import ActivityEvent, TaskAssignment
from onboarding.selectors import task_assignment_get_for_manager, user_dashboard_cache_invalidate


def task_assignment_approve(*, task_assignment_id: int, manager_id: int) -> TaskAssignment:
    with transaction.atomic():
        task_assignment = task_assignment_get_for_manager(
            task_assignment_id=task_assignment_id, manager_id=manager_id
        )

        if task_assignment.status == TaskAssignment.Status.APPROVED:
            raise ApplicationError("Task assignment is already approved.")

        if task_assignment.status != TaskAssignment.Status.COMPLETED:
            raise ApplicationError("Task assignment must be completed before it can be approved.")

        approved_at = timezone.now()

        task_assignment.approver_id = manager_id
        task_assignment.status = TaskAssignment.Status.APPROVED
        task_assignment.approved_at = approved_at
        task_assignment.save(update_fields=["approver_id", "status", "approved_at"])

        ActivityEvent.objects.create(
            user=task_assignment.assignee,
            event_type="task_approved",
            occurred_at=approved_at,
            metadata={"task_assignment_id": task_assignment.id, "task_id": task_assignment.task_id},
        )

        transaction.on_commit(
            lambda: user_dashboard_cache_invalidate(user_id=task_assignment.assignee_id)
        )

    return task_assignment
