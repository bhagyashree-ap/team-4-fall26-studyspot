"""Account routes, without trailing slashes like every other route."""

from django.urls import path

from .views import AccountView, AuthConfigView, UsernameView

urlpatterns = [
    path("auth/config", AuthConfigView.as_view(), name="auth-config"),
    path("account", AccountView.as_view(), name="account"),
    path("usernames/<str:username>", UsernameView.as_view(), name="username"),
]
