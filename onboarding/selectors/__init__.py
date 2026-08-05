"""Re-exports the public selectors, so callers import from the package path.

`from onboarding.selectors import module_list`, not
`from onboarding.selectors.modules import module_list`. Keeping the package path
stable is what let this layer become a package without touching a single call
site in `views/`, `services/`, or the management commands.

`_dashboard_cache_key` and `_DASHBOARD_CACHE_TTL` are deliberately absent: they
are private to `selectors/dashboard.py` and nothing outside it should reach them.
There is no `selectors/assessments.py`, because the assessments sub-domain has no
reads yet.
"""

from onboarding.selectors.activity import activity_event_list
from onboarding.selectors.dashboard import user_dashboard_cache_invalidate, user_dashboard_get
from onboarding.selectors.departments import department_activity_report_list
from onboarding.selectors.modules import module_get, module_list
from onboarding.selectors.onboarding_tasks import task_assignment_get_for_manager
from onboarding.selectors.skills import skill_search
from onboarding.selectors.users import user_get, user_list, user_reports_get, user_skills_list

__all__ = [
    "activity_event_list",
    "department_activity_report_list",
    "module_get",
    "module_list",
    "skill_search",
    "task_assignment_get_for_manager",
    "user_dashboard_cache_invalidate",
    "user_dashboard_get",
    "user_get",
    "user_list",
    "user_reports_get",
    "user_skills_list",
]
