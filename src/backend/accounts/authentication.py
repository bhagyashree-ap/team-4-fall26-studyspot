"""Authenticating requests with an Auth0 access token.

The browser logs in with Auth0 and sends the access token it receives as
``Authorization: Bearer <token>``. Verifying it needs nothing from Auth0 at
request time but its public signing keys, which is what lets the deployed API
check tokens with no route to the internet: Terraform reads the keys once at
apply time and passes them in as ``AUTH0_JWKS``.

A request with no token is anonymous rather than rejected, so that one class can
sit in front of public and private routes alike. A request with a token that
does not verify is rejected outright: a client that sent one meant to be
somebody, and quietly treating it as nobody would hide the problem.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from typing import Any

import jwt
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.request import Request

from .models import Account

#: Auth0 signs access tokens for a custom API with RS256 unless told otherwise.
#: Naming the one algorithm accepted is what stops a token from choosing its own.
ALGORITHMS = ["RS256"]

#: Where the browser sends the ID token from the same log-in, if it has one.
#: ``X-ID-Token`` on the wire.
ID_TOKEN_HEADER = "HTTP_X_ID_TOKEN"

#: Tolerated clock difference between Auth0 and the Lambda host, in seconds.
LEEWAY = 30


@dataclass(frozen=True)
class Identity:
    """What a verified token says about who sent it.

    ``email`` is blank when nothing the request carried said what it is, which
    is different from saying it changed: the stored address is then kept.
    """

    subject: str
    email: str
    email_verified: bool
    username: str


def configured() -> bool:
    """Whether accounts are switched on in this environment."""
    return bool(settings.AUTH0_DOMAIN and settings.AUTH0_CLIENT_ID and settings.AUTH0_AUDIENCE)


def issuer() -> str:
    # Auth0's issuer is the tenant URL with a trailing slash, and the comparison
    # is exact.
    return f"https://{settings.AUTH0_DOMAIN}/"


@cache
def _key_set(document: str) -> jwt.PyJWKSet:
    """Parse a JWKS document once per distinct value."""
    return jwt.PyJWKSet.from_dict(json.loads(document))


@cache
def _key_client(domain: str) -> jwt.PyJWKClient:
    """Fetch keys from the tenant, for development, which has a network."""
    return jwt.PyJWKClient(f"https://{domain}/.well-known/jwks.json", cache_keys=True)


def signing_key(token: str) -> Any:
    """The public key that should have signed ``token``, chosen by its ``kid``."""
    if settings.AUTH0_JWKS:
        kid = jwt.get_unverified_header(token).get("kid")
        for key in _key_set(settings.AUTH0_JWKS).keys:
            if key.key_id == kid:
                return key.key
        raise jwt.InvalidTokenError("The token was signed by a key this API does not know.")
    return _key_client(settings.AUTH0_DOMAIN).get_signing_key_from_jwt(token).key


def verify(token: str, id_token: str | None = None) -> Identity:
    """Check ``token`` and read the identity out of it.

    Raises :class:`jwt.InvalidTokenError` (or a subclass) for anything wrong
    with it, and :class:`jwt.PyJWKClientError` when the keys cannot be fetched.

    ``id_token`` is the ID token from the same log-in, which carries the email
    and whether Auth0 has verified it. It only ever adds those two facts: one
    that does not verify, or belongs to someone else, is ignored rather than
    trusted, and never fails a request the access token alone would pass.
    """
    claims = jwt.decode(
        token,
        signing_key(token),
        algorithms=ALGORITHMS,
        audience=settings.AUTH0_AUDIENCE,
        issuer=issuer(),
        leeway=LEEWAY,
        options={"require": ["exp", "iat", "sub"]},
    )

    # Auth0 leaves the email out of an access token. An optional post-login
    # Action can add it under a namespace (docs/source/accounts.md); without
    # one, it comes from the ID token instead.
    namespace = settings.AUTH0_CLAIM_NAMESPACE
    email = str(claims.get(f"{namespace}email") or "").strip().lower()
    email_verified = claims.get(f"{namespace}email_verified") is True

    if not email and id_token:
        profile = _id_token_claims(id_token, subject=claims["sub"])
        if profile is not None:
            email = str(profile.get("email") or "").strip().lower()
            email_verified = profile.get("email_verified") is True

    return Identity(
        subject=claims["sub"],
        email=email,
        email_verified=email_verified and bool(email),
        username=str(claims.get(f"{namespace}username") or "").strip(),
    )


def _id_token_claims(id_token: str, subject: str) -> dict[str, Any] | None:
    """The claims of ``id_token`` if it is genuine and about ``subject``."""
    try:
        claims = jwt.decode(
            id_token,
            signing_key(id_token),
            algorithms=ALGORITHMS,
            # An ID token is issued to the application, not to the API.
            audience=settings.AUTH0_CLIENT_ID,
            issuer=issuer(),
            leeway=LEEWAY,
            options={"require": ["exp", "iat", "sub"]},
        )
    except (jwt.InvalidTokenError, jwt.PyJWKClientError):
        return None
    return claims if claims["sub"] == subject else None


def account_for(identity: Identity) -> Account:
    """Find or create the account ``identity`` belongs to, refreshed from it."""
    with transaction.atomic():
        user, _ = get_user_model().objects.get_or_create(username=identity.subject)
        account, created = Account.objects.select_for_update().get_or_create(
            user=user,
            defaults={
                "email": identity.email,
                "email_verified": identity.email_verified,
                "username": identity.username,
            },
        )

        if not created:
            current: dict[str, Any] = {}
            # Nothing said what the email is, which is not news that it changed.
            if identity.email:
                current["email"] = identity.email
                current["email_verified"] = identity.email_verified
            # A token with no username leaves alone the one chosen on StudySpot.
            if identity.username:
                current["username"] = identity.username
            changed = [name for name, value in current.items() if getattr(account, name) != value]
            if changed:
                for name in changed:
                    setattr(account, name, current[name])
                try:
                    with transaction.atomic():
                        account.save(update_fields=[*changed, "updated_at"])
                except IntegrityError:
                    # Auth0's username clashes with one a student chose here.
                    # The account keeps its own rather than refusing the log-in.
                    account.refresh_from_db()
                    if "username" in changed:
                        changed.remove("username")
                    for name in changed:
                        setattr(account, name, current[name])
                    if changed:
                        account.save(update_fields=[*changed, "updated_at"])

    return account


class Auth0Authentication(BaseAuthentication):
    """DRF authentication from an Auth0 bearer token."""

    keyword = b"bearer"

    def authenticate(self, request: Request) -> tuple[Any, Identity] | None:
        header = get_authorization_header(request).split()
        if not header or header[0].lower() != self.keyword:
            return None

        if len(header) != 2:
            raise AuthenticationFailed("The Authorization header must be 'Bearer <token>'.")

        if not configured():
            raise AuthenticationFailed("Accounts are not configured on this server.")

        try:
            identity = verify(header[1].decode("ascii"), request.META.get(ID_TOKEN_HEADER))
        except (UnicodeDecodeError, jwt.InvalidTokenError) as error:
            raise AuthenticationFailed("The access token is not valid.") from error
        except jwt.PyJWKClientError as error:
            raise AuthenticationFailed("The signing keys could not be loaded.") from error

        return account_for(identity).user, identity

    def authenticate_header(self, request: Request) -> str:
        # Present, so DRF answers a missing or bad token with 401 rather than 403.
        return 'Bearer realm="api"'
