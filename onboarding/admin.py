from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from onboarding.models import (
    ActivityEvent,
    Assessment,
    AssessmentAttempt,
    AssessmentQuestion,
    Department,
    ModuleAssignment,
    OnboardingModule,
    OnboardingTask,
    Skill,
    TaskAssignment,
    User,
    UserSkill,
)
from onboarding.services import skill_create


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = DjangoUserAdmin.list_display + ("department", "manager")
    list_filter = DjangoUserAdmin.list_filter + ("department",)
    fieldsets = DjangoUserAdmin.fieldsets + (("Onboarding", {"fields": ("department", "manager")}),)


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(OnboardingModule)
class OnboardingModuleAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "order")
    list_filter = ("category",)
    search_fields = ("title",)


@admin.register(ModuleAssignment)
class ModuleAssignmentAdmin(admin.ModelAdmin):
    list_display = ("user", "module", "status", "due_date", "overdue")
    list_filter = ("status",)
    list_select_related = ("user", "module")

    @admin.display(boolean=True)
    def overdue(self, obj: ModuleAssignment) -> bool:
        return obj.is_overdue


class AssessmentQuestionInline(admin.TabularInline):
    model = AssessmentQuestion
    extra = 1


@admin.register(Assessment)
class AssessmentAdmin(admin.ModelAdmin):
    list_display = ("module", "passing_score")
    inlines = [AssessmentQuestionInline]


@admin.register(AssessmentQuestion)
class AssessmentQuestionAdmin(admin.ModelAdmin):
    list_display = ("assessment", "text", "order")
    list_select_related = ("assessment",)


@admin.register(AssessmentAttempt)
class AssessmentAttemptAdmin(admin.ModelAdmin):
    list_display = ("user", "assessment", "score", "attempted_at")
    list_filter = ("assessment",)
    search_fields = ("user__username",)
    date_hierarchy = "attempted_at"
    list_select_related = ("user", "assessment")
    readonly_fields = ("attempted_at",)


@admin.register(OnboardingTask)
class OnboardingTaskAdmin(admin.ModelAdmin):
    list_display = ("title", "requires_approval")
    list_filter = ("requires_approval",)
    search_fields = ("title",)
    filter_horizontal = ("departments",)


@admin.register(TaskAssignment)
class TaskAssignmentAdmin(admin.ModelAdmin):
    list_display = ("task", "assignee", "approver", "status")
    list_filter = ("status",)
    list_select_related = ("task", "assignee", "approver")
    readonly_fields = ("completed_at", "approved_at")


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display = ("name", "is_embedded")
    search_fields = ("name", "description")
    exclude = ("embedding",)

    @admin.display(boolean=True, description="Embedded")
    def is_embedded(self, obj: Skill) -> bool:
        return obj.embedding is not None

    def save_model(self, request, obj, form, change):
        """Routes an admin create through skill_create so it gets embedded.

        Delegating to the service rather than calling super() is deliberate.
        `embedding` is excluded from this form, so a plain admin save would
        write a row with a null vector that never appears in skill search, and
        nothing in the interface would say so. This is the same rule that
        applies everywhere else in the project, applied to a second entry
        point: the admin is a caller of the service layer, not an alternative
        to it.

        Django's own permission check has already confirmed the caller is staff
        with add_skill before this runs, which is the same answer IsStaff gives
        SkillCreateApi.
        """
        # Known gap, left open deliberately rather than hidden: editing a
        # description here does not re-embed, so the vector goes stale. Closing
        # it needs a skill_update service and a second trigger for the same
        # task, which is out of scope for a phase whose goal is one task running
        # end to end. The is_embedded column above makes the null case visible;
        # the stale case is not visible, and that is the cost of deferring.
        if change:
            super().save_model(request, obj, form, change)
            return

        skill, _ = skill_create(name=obj.name, description=obj.description)
        # The admin reads obj.pk afterwards to build its redirect and log entry,
        # so the id from the service has to land on the instance it was handed.
        obj.pk = skill.pk


@admin.register(UserSkill)
class UserSkillAdmin(admin.ModelAdmin):
    list_display = ("user", "skill", "proficiency")
    list_filter = ("proficiency",)
    list_select_related = ("user", "skill")


@admin.register(ActivityEvent)
class ActivityEventAdmin(admin.ModelAdmin):
    list_display = ("user", "event_type", "occurred_at")
    list_filter = ("event_type",)
    search_fields = ("user__username",)
    date_hierarchy = "occurred_at"
    list_select_related = ("user",)
    readonly_fields = ("occurred_at",)
