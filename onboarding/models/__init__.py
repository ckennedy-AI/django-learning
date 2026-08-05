"""Re-exports every model in the app.

This is not a convenience, it is how Django discovers the models. A model class
that is not imported here is invisible to the app registry, and `makemigrations`
generates a `DeleteModel` for it, which reads as a schema change rather than as
the missing import it actually is. See gotcha 14 in CLAUDE.md. After touching
anything in this package, run `makemigrations --check --dry-run` and expect no
changes.

The import order below is alphabetical because Ruff's isort rule enforces it, not
because it reflects the dependency graph. Nothing here depends on the order: each
submodule imports its siblings directly rather than through this file, which is
also what keeps a submodule from importing a half-initialised `onboarding.models`.
"""

from onboarding.models.activity import ActivityEvent
from onboarding.models.assessments import Assessment, AssessmentAttempt, AssessmentQuestion
from onboarding.models.departments import Department
from onboarding.models.modules import (
    ModuleAssignment,
    ModuleAssignmentQuerySet,
    OnboardingModule,
)
from onboarding.models.onboarding_tasks import OnboardingTask, TaskAssignment
from onboarding.models.skills import Skill, UserSkill
from onboarding.models.users import User

__all__ = [
    "ActivityEvent",
    "Assessment",
    "AssessmentAttempt",
    "AssessmentQuestion",
    "Department",
    "ModuleAssignment",
    "ModuleAssignmentQuerySet",
    "OnboardingModule",
    "OnboardingTask",
    "Skill",
    "TaskAssignment",
    "User",
    "UserSkill",
]
