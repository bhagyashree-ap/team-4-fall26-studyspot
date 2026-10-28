"""Account routes.

``GET /auth/config`` is public: it tells the browser which Auth0 tenant to log
in with, so that the frontend build carries no environment of its own.
``/account`` needs a valid access token.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.db import IntegrityError, transaction
from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .authentication import Auth0Authentication, configured
from .models import Account
from .serializers import AccountSerializer, CompleteSignUpSerializer, username_problem


class SignUpAlreadyComplete(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "This account has already finished signing up."
    default_code = "conflict"


class AuthConfigView(APIView):
    """The public Auth0 settings the browser needs to start a log-in."""

    authentication_classes: list[type] = []
    permission_classes: list[type] = []

    def get(self, request: Request) -> Response:
        if not configured():
            return Response({"enabled": False})
        return Response(
            {
                "enabled": True,
                "domain": settings.AUTH0_DOMAIN,
                "client_id": settings.AUTH0_CLIENT_ID,
                "audience": settings.AUTH0_AUDIENCE,
            }
        )


class AccountView(APIView):
    """The logged-in person's own account.

    ``GET`` creates it on the first request after an Auth0 sign-up, so there is
    no separate registration call to forget. ``POST`` finishes sign-up by
    choosing student or business, once.
    """

    authentication_classes = [Auth0Authentication]
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        return Response(AccountSerializer(self._account(request)).data)

    def post(self, request: Request) -> Response:
        account = self._account(request)
        if account.account_type:
            raise SignUpAlreadyComplete()

        serializer = CompleteSignUpSerializer(data=request.data, context={"account": account})
        serializer.is_valid(raise_exception=True)
        data: dict[str, Any] = serializer.validated_data

        account.account_type = data["account_type"]
        account.business_name = data["business_name"]
        account.username = data["username"]
        try:
            with transaction.atomic():
                account.save(
                    update_fields=["account_type", "business_name", "username", "updated_at"]
                )
        except IntegrityError as error:
            # Someone else took the name between the check and the save.
            raise ValidationError(
                {"username": "That username is taken."}, code="username_taken"
            ) from error
        return Response(AccountSerializer(account).data, status=status.HTTP_201_CREATED)

    @staticmethod
    def _account(request: Request) -> Account:
        return request.user.account


class UsernameView(APIView):
    """Whether a username can still be chosen, for the sign-up form to say so.

    Public, like the sign-up form that asks: it answers before anyone has an
    account. It says only whether a name is free, which submitting the form
    would reveal anyway.
    """

    authentication_classes: list[type] = []
    permission_classes: list[type] = []

    def get(self, request: Request, username: str) -> Response:
        problem = username_problem(username.strip())
        code, message = problem if problem is not None else (None, None)
        return Response(
            {
                "username": username,
                "available": problem is None,
                "reason": code,
                "message": message,
            }
        )
