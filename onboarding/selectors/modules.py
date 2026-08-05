from django.db.models import QuerySet
from django.shortcuts import get_object_or_404

from onboarding.models import OnboardingModule


def module_list() -> QuerySet[OnboardingModule]:
    return OnboardingModule.objects.all()


def module_get(*, module_id: int) -> OnboardingModule:
    return get_object_or_404(OnboardingModule, id=module_id)
