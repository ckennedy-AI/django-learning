from django.urls import path

from onboarding.views import (
    ActivityEventListApi,
    DepartmentActivityReportApi,
    ModuleDetailApi,
    ModuleListApi,
    MyDashboardApi,
    SkillCreateApi,
    SkillSearchApi,
    TaskApprovalApi,
    UserDetailApi,
    UserListApi,
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
    path("users/", UserListApi.as_view(), name="user-list"),
    path("users/<int:user_id>/", UserDetailApi.as_view(), name="user-detail"),
    path("users/<int:user_id>/skills/", UserSkillsApi.as_view(), name="user-skills"),
    path("users/<int:user_id>/reports/", UserReportsApi.as_view(), name="user-reports"),
]

department_patterns = [
    path("departments/activity-report/", DepartmentActivityReportApi.as_view(), name="department-activity-report"),
]

skill_patterns = [
    # POST only. There is no SkillListApi, so `skills/` answers 405 to a GET,
    # which is the honest response: one API class per operation means the
    # collection read does not exist until an endpoint needs it.
    path("skills/", SkillCreateApi.as_view(), name="skill-create"),
    path("skills/search/", SkillSearchApi.as_view(), name="skill-search"),
]

task_assignment_patterns = [
    path("task-assignments/<int:task_assignment_id>/approve/", TaskApprovalApi.as_view(), name="task-assignment-approve"),
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
