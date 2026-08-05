from datetime import date

from django.core.cache import cache
from django.db.models import F, QuerySet
from django.shortcuts import get_object_or_404
from pgvector.django import CosineDistance

from onboarding.models import (
    ActivityEvent,
    Department,
    ModuleAssignment,
    OnboardingModule,
    Skill,
    TaskAssignment,
    User,
    UserSkill,
)


def module_list() -> QuerySet[OnboardingModule]:
    return OnboardingModule.objects.all()


def module_get(*, module_id: int) -> OnboardingModule:
    return get_object_or_404(OnboardingModule, id=module_id)


def activity_event_list(*, filters: dict | None = None) -> QuerySet[ActivityEvent]:
    filters = filters or {}

    queryset = ActivityEvent.objects.all()

    if user_id := filters.get("user_id"):
        queryset = queryset.filter(user_id=user_id)

    if event_type := filters.get("event_type"):
        queryset = queryset.filter(event_type=event_type)

    return queryset


def user_get(*, user_id: int) -> User:
    return get_object_or_404(User.objects.select_related("department", "manager"), id=user_id)


def user_skills_list(*, user_id: int) -> QuerySet[UserSkill]:
    return UserSkill.objects.filter(user_id=user_id).select_related("skill")


def user_reports_get(*, user_id: int) -> User:
    return get_object_or_404(
        User.objects.select_related("manager").prefetch_related("direct_reports"),
        id=user_id,
    )


def department_activity_report_list() -> list[dict]:
    """One row per department: headcount, module completion rate, activity volume.

    Deliberately unoptimized. This is an occasional admin report, not a
    per-request hot path, so it runs one query per metric per department
    instead of a single annotated aggregate query. Documented in CLAUDE.md's
    endpoint table as a conscious tradeoff, not an oversight.
    """
    report = []

    for department in Department.objects.all():
        employee_count = department.employees.count()

        assignments = ModuleAssignment.objects.filter(user__department=department)
        total_assignments = assignments.count()
        completed_assignments = assignments.filter(status=ModuleAssignment.Status.COMPLETED).count()
        completion_percentage = (
            round(completed_assignments / total_assignments * 100, 1) if total_assignments else 0.0
        )

        activity_event_count = ActivityEvent.objects.filter(user__department=department).count()

        report.append(
            {
                "department_id": department.id,
                "department_name": department.name,
                "employee_count": employee_count,
                "completion_percentage": completion_percentage,
                "activity_event_count": activity_event_count,
            }
        )

    return report


def skill_search(*, embedding: list[float], limit: int = 10) -> QuerySet[Skill]:
    return Skill.objects.annotate(distance=CosineDistance("embedding", embedding)).order_by(
        "distance"
    )[:limit]


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
