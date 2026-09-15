from django.contrib.auth.views import LogoutView
from django.urls import include, path

from library.views import PrivateLoginView

urlpatterns = [
    path("login/", PrivateLoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("", include("library.urls")),
]
