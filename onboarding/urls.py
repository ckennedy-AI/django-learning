from django.urls import path

from onboarding.views import ModuleDetailApi, ModuleListApi

module_patterns = [
    path("modules/", ModuleListApi.as_view(), name="module-list"),
    path("modules/<int:module_id>/", ModuleDetailApi.as_view(), name="module-detail"),
]

urlpatterns = [
    *module_patterns,
]
