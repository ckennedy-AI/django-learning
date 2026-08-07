"""Re-exports the eleven API classes, so `urls.py` imports from the package path.

`urls.py` was not touched when this layer became a package, which is the point:
`from onboarding.views import ModuleListApi` still resolves.

Only API classes are exported. Notably `embed_texts`, which `views/skills.py`
imports for `SkillSearchApi`, is not re-exported here: nothing outside that module
has a reason to reach it, and the test that mocks it patches
`onboarding.views.skills.embed_texts` at its real location.

There is no `views/assessments.py`, because the assessments sub-domain has no
endpoints yet.
"""

from onboarding.views.activity import ActivityEventListApi
from onboarding.views.dashboard import MyDashboardApi
from onboarding.views.departments import DepartmentActivityReportApi
from onboarding.views.modules import ModuleDetailApi, ModuleListApi
from onboarding.views.onboarding_tasks import TaskApprovalApi
from onboarding.views.skills import SkillCreateApi, SkillSearchApi
from onboarding.views.users import UserDetailApi, UserListApi, UserReportsApi, UserSkillsApi

__all__ = [
    "ActivityEventListApi",
    "DepartmentActivityReportApi",
    "ModuleDetailApi",
    "ModuleListApi",
    "MyDashboardApi",
    "SkillCreateApi",
    "SkillSearchApi",
    "TaskApprovalApi",
    "UserDetailApi",
    "UserListApi",
    "UserReportsApi",
    "UserSkillsApi",
]
