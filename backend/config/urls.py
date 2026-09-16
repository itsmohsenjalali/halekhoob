from django.conf import settings
from django.contrib.auth.views import LogoutView
from django.urls import include, path

from library.views import PrivateLoginView, health

urlpatterns = [path("healthz/", health), path("api/v1/", include("library.api"))]
if settings.LEGACY_UI_ENABLED:
    urlpatterns += [path("login/", PrivateLoginView.as_view(), name="login"),
                    path("logout/", LogoutView.as_view(), name="logout"), path("", include("library.urls"))]
