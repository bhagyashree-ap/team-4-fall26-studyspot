"""Shapes of the account routes' requests and responses."""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import Account, AccountType, username_validator


class AccountSerializer(serializers.ModelSerializer):
    """An account as its owner sees it.

    ``account_type`` is ``null`` until sign-up is finished, which is how the
    frontend knows to ask.
    """

    account_type = serializers.SerializerMethodField()

    class Meta:
        model = Account
        fields = (
            "email",
            "email_verified",
            "username",
            "account_type",
            "business_name",
            "created_at",
        )
        read_only_fields = fields

    def get_account_type(self, account: Account) -> str | None:
        return str(account.account_type) or None


def is_student_email(email: str) -> bool:
    """Whether ``email`` is at one of the domains a student account allows."""
    _, _, domain = email.rpartition("@")
    domain = domain.lower()
    return any(
        domain == allowed or domain.endswith(f".{allowed}")
        for allowed in settings.STUDENT_EMAIL_DOMAINS
    )


class CompleteSignUpSerializer(serializers.Serializer):
    """The one decision Auth0's sign-up form does not make: which kind of account.

    Validated against the account it will be applied to, because what is
    allowed depends on the email Auth0 verified, not on anything in the body.
    """

    account_type = serializers.ChoiceField(choices=AccountType.choices)
    business_name = serializers.CharField(
        max_length=200, required=False, allow_blank=True, trim_whitespace=True
    )
    #: Only for a student whose Auth0 log-in did not come with one.
    username = serializers.CharField(
        max_length=30, required=False, allow_blank=True, trim_whitespace=True
    )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        account: Account = self.context["account"]
        account_type = attrs["account_type"]
        business_name = attrs.get("business_name", "")
        chosen = attrs.get("username", "")
        username = str(account.username)

        if not account.email_verified:
            raise serializers.ValidationError(
                {"email": "Verify your email address before finishing sign-up."},
                code="email_unverified",
            )

        if account_type == AccountType.STUDENT:
            if not is_student_email(str(account.email)):
                raise serializers.ValidationError(
                    {"email": "A student account needs a university email address."},
                    code="not_a_student_email",
                )
            if username:
                # Auth0 already holds one, and it is what they log in with.
                if chosen and chosen.casefold() != username.casefold():
                    raise serializers.ValidationError(
                        {"username": f"Your username is already {username}."},
                        code="not_allowed",
                    )
            else:
                username = self._choose(chosen, account)
            if business_name:
                raise serializers.ValidationError(
                    {"business_name": "Only a business account has a business name."},
                    code="not_allowed",
                )

        if account_type == AccountType.BUSINESS and not business_name:
            raise serializers.ValidationError(
                {"business_name": "A business account needs a business name."},
                code="required",
            )

        return {
            "account_type": account_type,
            "business_name": business_name,
            "username": username,
        }

    @staticmethod
    def _choose(username: str, account: Account) -> str:
        """Check a username a student picked here."""
        problem = username_problem(username, exclude=account)
        if problem is not None:
            code, message = problem
            raise serializers.ValidationError({"username": message}, code=code)
        return username


def username_problem(username: str, exclude: Account | None = None) -> tuple[str, str] | None:
    """Why ``username`` cannot be chosen, as ``(code, message)``, or ``None``.

    Shared by sign-up and the availability check, so the form's live answer and
    the final one cannot disagree.
    """
    if not username:
        return "required", "Choose a username."
    try:
        username_validator(username)
    except DjangoValidationError as error:
        return "invalid_username", str(error.messages[0])
    taken = Account.objects.filter(username__iexact=username)
    if exclude is not None:
        taken = taken.exclude(pk=exclude.pk)
    if taken.exists():
        return "username_taken", "That username is taken."
    return None
