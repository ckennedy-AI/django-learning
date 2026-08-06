"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView


class ThrottledTokenObtainPairView(TokenObtainPairView):
    # The stock view has no throttle_scope. UPDATE_LAST_LOGIN writes to the
    # database on every successful call, which Simple JWT's own docs flag as
    # a potential DoS vector without a throttle in front of it. The rate
    # itself is DEFAULT_THROTTLE_RATES["token_obtain"] in settings.py.
    throttle_scope = "token_obtain"


urlpatterns = [
    path("admin/", admin.site.urls),
    # Not part of the onboarding domain's endpoint surface: these are stock
    # Simple JWT views, not <Entity><Action>Api classes owned by a
    # sub-domain, so they live beside the admin registration rather than in
    # onboarding/urls.py or onboarding/views/.
    path("api/token/", ThrottledTokenObtainPairView.as_view(), name="token-obtain"),
    path("api/token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("api/", include("onboarding.urls")),
]

if settings.DEBUG_TOOLBAR_ENABLED:
    urlpatterns += [path("__debug__/", include("debug_toolbar.urls"))]
