"""Account routes, without trailing slashes like every other route."""

from django.urls import path

from .views import (
    AccountView,
    AuthConfigView,
    PublicStudentProfileView,
    StudentDirectMessageView,
    StudentDirectoryView,
    StudentProfileView,
    UsernameView,
)

urlpatterns = [
    path("auth/config", AuthConfigView.as_view(), name="auth-config"),
    path("account", AccountView.as_view(), name="account"),
    path("usernames/<str:username>", UsernameView.as_view(), name="username"),
    path("people", StudentDirectoryView.as_view(), name="student-directory"),
    path("people/me", StudentProfileView.as_view(), name="student-profile"),
    path(
        "people/<str:username>/dm",
        StudentDirectMessageView.as_view(),
        name="student-direct-message",
    ),
    path(
        "people/<str:username>", PublicStudentProfileView.as_view(), name="public-student-profile"
    ),
]
