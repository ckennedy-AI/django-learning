from django.db.models import F, QuerySet, Value
from django.db.models.functions import Concat, Trim
from django.shortcuts import get_object_or_404

from onboarding.models import User, UserSkill


def user_get(*, user_id: int) -> User:
    return get_object_or_404(User.objects.select_related("department", "manager"), id=user_id)


def user_list(*, filters: dict | None = None) -> QuerySet[dict]:
    """The company directory, one flattened row per user.

    `.values()` with annotations rather than model instances plus
    `select_related`: nothing here is ever touched as a related object again,
    just plain columns, so there is no second hop for `select_related` to
    collapse. `department` and `manager` are both nullable, so Django emits
    `LEFT OUTER JOIN` for both `F()` lookups, matching the two `LEFT JOIN`s in
    the equivalent raw SQL. `Concat` coalesces null name parts to an empty
    string the same way Postgres's `CONCAT()` function does, so `manager_name`
    is `""` rather than `NULL` when a user has no manager, and `Trim` removes
    the leading or trailing space that concatenating a blank part would leave.

    `username` is an exact match, not a search: it is unique on `User`, so a
    caller filtering by it already knows the one row they want, the same way
    `ActivityEventListApi`'s `event_type` filter is an exact match rather than
    a substring search.
    """
    filters = filters or {}

    queryset = User.objects.annotate(
        name=Trim(Concat("first_name", Value(" "), "last_name")),
        manager_name=Trim(Concat("manager__first_name", Value(" "), "manager__last_name")),
        department_name=F("department__name"),
    )

    if username := filters.get("username"):
        queryset = queryset.filter(username=username)

    return queryset.values(
        "id",
        "username",
        "name",
        "email",
        "is_staff",
        "is_active",
        "manager_name",
        "department_name",
    )


def user_skills_list(*, user_id: int) -> QuerySet[UserSkill]:
    """One user's skills, with the skill joined in.

    Lives here rather than in `selectors/skills.py` because it serves
    `UserSkillsApi`, which is a user endpoint. Placement follows the sub-domain of
    the endpoint served, not the entity read, so that every layer of one endpoint
    shares a filename.

    `select_related("skill")` collapses the second hop. `User` has no
    `ManyToManyField` to `Skill`, so this is a reverse FK to `UserSkill` followed
    by a forward FK to `Skill`, and that forward hop is the N+1. See
    `manage.py benchmark_user_skills`.
    """
    return UserSkill.objects.filter(user_id=user_id).select_related("skill")


def user_reports_get(*, user_id: int) -> User:
    return get_object_or_404(
        User.objects.select_related("manager").prefetch_related("direct_reports"),
        id=user_id,
    )
