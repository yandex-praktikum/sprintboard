from django.urls import include, path
from core import auth
from core.http import health

urlpatterns = [
    path("api/health/", health),
    path("api/auth/csrf/", auth.csrf),
    path("api/auth/register/", auth.register),
    path("api/auth/login/", auth.sign_in),
    path("api/auth/logout/", auth.sign_out),
    path("api/auth/me/", auth.me),
    path("api/", include("board.urls")),
]
