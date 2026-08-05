from django.urls import path

from onboarding.views import (
    ActivityEventListApi,
    DepartmentActivityReportApi,
    ModuleDetailApi,
    ModuleListApi,
    MyDashboardApi,
    SkillSearchApi,
    TaskApprovalApi,
    UserDetailApi,
    UserReportsApi,
    UserSkillsApi,
)

module_patterns = [
    path("modules/", ModuleListApi.as_view(), name="module-list"),
    path("modules/<int:module_id>/", ModuleDetailApi.as_view(), name="module-detail"),
]

activity_event_patterns = [
    path("activity-events/", ActivityEventListApi.as_view(), name="activity-event-list"),
]

user_patterns = [
    path("users/<int:user_id>/", UserDetailApi.as_view(), name="user-detail"),
    path("users/<int:user_id>/skills/", UserSkillsApi.as_view(), name="user-skills"),
    path("users/<int:user_id>/reports/", UserReportsApi.as_view(), name="user-reports"),
]

department_patterns = [
    path(
        "departments/activity-report/",
        DepartmentActivityReportApi.as_view(),
        name="department-activity-report",
    ),
]

skill_patterns = [
    path("skills/search/", SkillSearchApi.as_view(), name="skill-search"),
]

task_assignment_patterns = [
    path(
        "task-assignments/<int:task_assignment_id>/approve/",
        TaskApprovalApi.as_view(),
        name="task-assignment-approve",
    ),
]

dashboard_patterns = [
    path("dashboard/", MyDashboardApi.as_view(), name="my-dashboard"),
]

urlpatterns = [
    *module_patterns,
    *activity_event_patterns,
    *user_patterns,
    *department_patterns,
    *skill_patterns,
    *task_assignment_patterns,
    *dashboard_patterns,
]
