from onboarding.models import ActivityEvent, Department, ModuleAssignment


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
