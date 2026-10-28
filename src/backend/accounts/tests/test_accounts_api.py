"""Tests for the account routes and the Auth0 token check behind them.

No Auth0 tenant is involved. Each test signs its own tokens with a key generated
here and hands the matching public key to the API as ``AUTH0_JWKS``, which is
exactly how a deployment receives them, so the verification path under test is
the one that runs in production.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Iterator
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from django.contrib.auth import get_user_model
from jwt.algorithms import RSAAlgorithm
from jwt.utils import base64url_encode

from accounts.models import Account, AccountType

DOMAIN = "studyspot-test.us.auth0.com"
AUDIENCE = "https://api.studyspot.test"
NAMESPACE = "https://studyspot.app/"
KID = "test-key"

Token = Callable[..., str]


def rsa_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def jwks(key: rsa.RSAPrivateKey, kid: str = KID) -> str:
    public = json.loads(RSAAlgorithm.to_jwk(key.public_key()))
    return json.dumps({"keys": [{**public, "kid": kid, "use": "sig", "alg": "RS256"}]})


@pytest.fixture(scope="module")
def signing_key() -> rsa.RSAPrivateKey:
    return rsa_key()


@pytest.fixture(autouse=True)
def auth0(settings: Any, signing_key: rsa.RSAPrivateKey) -> Iterator[None]:
    settings.AUTH0_DOMAIN = DOMAIN
    settings.AUTH0_CLIENT_ID = "spa-client-id"
    settings.AUTH0_AUDIENCE = AUDIENCE
    settings.AUTH0_JWKS = jwks(signing_key)
    settings.AUTH0_CLAIM_NAMESPACE = NAMESPACE
    settings.STUDENT_EMAIL_DOMAINS = ("edu",)
    yield


@pytest.fixture
def token(signing_key: rsa.RSAPrivateKey) -> Token:
    """Sign an access token the way Auth0 and the post-login Action would."""

    def sign(
        sub: str = "auth0|student",
        email: str = "ada@nyu.edu",
        email_verified: bool = True,
        username: str = "ada",
        key: rsa.RSAPrivateKey | None = None,
        kid: str = KID,
        **overrides: Any,
    ) -> str:
        now = int(time.time())
        claims = {
            "iss": f"https://{DOMAIN}/",
            "aud": [AUDIENCE, f"https://{DOMAIN}/userinfo"],
            "sub": sub,
            "iat": now,
            "exp": now + 3600,
            f"{NAMESPACE}email": email,
            f"{NAMESPACE}email_verified": email_verified,
            f"{NAMESPACE}username": username,
            **overrides,
        }
        return jwt.encode(claims, key or signing_key, algorithm="RS256", headers={"kid": kid})

    return sign


def bearer(value: str) -> dict[str, str]:
    return {"HTTP_AUTHORIZATION": f"Bearer {value}"}


class TestAuthConfig:
    def test_publishes_what_the_browser_needs(self, client: Any) -> None:
        body = client.get("/auth/config").json()

        assert body == {
            "enabled": True,
            "domain": DOMAIN,
            "client_id": "spa-client-id",
            "audience": AUDIENCE,
        }

    def test_reports_disabled_when_unconfigured(self, client: Any, settings: Any) -> None:
        settings.AUTH0_DOMAIN = ""

        assert client.get("/auth/config").json() == {"enabled": False}

    def test_does_not_touch_the_database(self, client: Any) -> None:
        # No `db` fixture: any query would fail the test.
        assert client.get("/auth/config").status_code == 200


@pytest.mark.django_db
class TestAuthentication:
    def test_rejects_a_request_without_a_token(self, client: Any) -> None:
        response = client.get("/account")

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "unauthorized"
        assert response["WWW-Authenticate"].startswith("Bearer")

    def test_rejects_a_malformed_token(self, client: Any) -> None:
        response = client.get("/account", **bearer("not-a-jwt"))

        assert response.status_code == 401
        assert response.json()["error"]["message"] == "The access token is not valid."

    def test_rejects_a_token_signed_by_another_key(self, client: Any, token: Token) -> None:
        response = client.get("/account", **bearer(token(key=rsa_key())))

        assert response.status_code == 401

    def test_rejects_a_token_with_an_unknown_key_id(self, client: Any, token: Token) -> None:
        assert client.get("/account", **bearer(token(kid="rotated"))).status_code == 401

    def test_rejects_an_expired_token(self, client: Any, token: Token) -> None:
        past = int(time.time()) - 7200

        response = client.get("/account", **bearer(token(iat=past, exp=past + 60)))

        assert response.status_code == 401

    def test_rejects_a_token_for_another_api(self, client: Any, token: Token) -> None:
        response = client.get("/account", **bearer(token(aud="https://elsewhere.test")))

        assert response.status_code == 401

    def test_rejects_a_token_from_another_tenant(self, client: Any, token: Token) -> None:
        response = client.get("/account", **bearer(token(iss="https://evil.auth0.com/")))

        assert response.status_code == 401

    def test_rejects_an_unsigned_token(self, client: Any) -> None:
        # Assembled by hand: the classic attack is a token that names "none" as
        # its algorithm and carries no signature at all.
        now = int(time.time())
        header = {"alg": "none", "typ": "JWT", "kid": KID}
        claims = {
            "sub": "auth0|x",
            "aud": AUDIENCE,
            "iss": f"https://{DOMAIN}/",
            "iat": now,
            "exp": now + 3600,
        }
        unsigned = ".".join(
            base64url_encode(json.dumps(part).encode()).decode() for part in (header, claims)
        )
        unsigned += "."

        assert client.get("/account", **bearer(unsigned)).status_code == 401

    def test_rejects_tokens_when_accounts_are_off(
        self, client: Any, token: Token, settings: Any
    ) -> None:
        settings.AUTH0_AUDIENCE = ""

        assert client.get("/account", **bearer(token())).status_code == 401


@pytest.mark.django_db
class TestGetAccount:
    def test_creates_the_account_on_first_request(self, client: Any, token: Token) -> None:
        response = client.get("/account", **bearer(token()))

        assert response.status_code == 200
        body = response.json()
        assert body["email"] == "ada@nyu.edu"
        assert body["email_verified"] is True
        assert body["username"] == "ada"
        assert body["account_type"] is None
        assert body["business_name"] == ""
        assert Account.objects.get().user.username == "auth0|student"

    def test_does_not_create_a_second_account(self, client: Any, token: Token) -> None:
        client.get("/account", **bearer(token()))
        client.get("/account", **bearer(token()))

        assert Account.objects.count() == 1
        assert get_user_model().objects.count() == 1

    def test_follows_changes_made_in_auth0(self, client: Any, token: Token) -> None:
        client.get("/account", **bearer(token(email_verified=False)))

        body = client.get(
            "/account", **bearer(token(email="Ada@NYU.edu", email_verified=True))
        ).json()

        assert body["email"] == "ada@nyu.edu"
        assert body["email_verified"] is True

    def test_does_not_expose_the_auth0_subject(self, client: Any, token: Token) -> None:
        body = client.get("/account", **bearer(token())).json()

        assert "auth0|student" not in json.dumps(body)


@pytest.mark.django_db
class TestCompleteSignUp:
    def test_makes_a_student_account(self, client: Any, token: Token) -> None:
        response = client.post(
            "/account",
            {"account_type": "student"},
            content_type="application/json",
            **bearer(token()),
        )

        assert response.status_code == 201
        assert response.json()["account_type"] == "student"
        assert Account.objects.get().account_type == AccountType.STUDENT

    def test_accepts_a_university_subdomain(self, client: Any, token: Token) -> None:
        response = client.post(
            "/account",
            {"account_type": "student"},
            content_type="application/json",
            **bearer(token(email="grace@cims.nyu.edu")),
        )

        assert response.status_code == 201

    def test_refuses_a_student_without_a_university_email(self, client: Any, token: Token) -> None:
        response = client.post(
            "/account",
            {"account_type": "student"},
            content_type="application/json",
            **bearer(token(email="ada@gmail.com")),
        )

        assert response.status_code == 422
        [detail] = response.json()["error"]["details"]
        assert detail["field"] == "body.email"
        assert detail["type"] == "not_a_student_email"

    def test_is_not_fooled_by_edu_in_the_local_part(self, client: Any, token: Token) -> None:
        response = client.post(
            "/account",
            {"account_type": "student"},
            content_type="application/json",
            **bearer(token(email="me.edu@gmail.com")),
        )

        assert response.status_code == 422

    def test_refuses_an_unverified_email(self, client: Any, token: Token) -> None:
        response = client.post(
            "/account",
            {"account_type": "student"},
            content_type="application/json",
            **bearer(token(email_verified=False)),
        )

        assert response.status_code == 422
        assert response.json()["error"]["details"][0]["type"] == "email_unverified"

    def test_refuses_a_student_without_a_username(self, client: Any, token: Token) -> None:
        response = client.post(
            "/account",
            {"account_type": "student"},
            content_type="application/json",
            **bearer(token(username="")),
        )

        assert response.status_code == 422
        [detail] = response.json()["error"]["details"]
        assert detail["field"] == "body.username"
        assert detail["type"] == "required"

    def test_lets_a_student_without_one_choose_a_username(self, client: Any, token: Token) -> None:
        # What a Google log-in, or a connection without usernames, looks like.
        response = client.post(
            "/account",
            {"account_type": "student", "username": "  grace_h  "},
            content_type="application/json",
            **bearer(token(username="")),
        )

        assert response.status_code == 201
        assert response.json()["username"] == "grace_h"

    def test_keeps_a_chosen_username_when_the_token_has_none(
        self, client: Any, token: Token
    ) -> None:
        client.post(
            "/account",
            {"account_type": "student", "username": "grace_h"},
            content_type="application/json",
            **bearer(token(username="")),
        )

        body = client.get("/account", **bearer(token(username=""))).json()

        assert body["username"] == "grace_h"

    @pytest.mark.parametrize("username", ["ab", "has space", "émile", "x" * 31, "a@b"])
    def test_refuses_a_malformed_username(self, client: Any, token: Token, username: str) -> None:
        response = client.post(
            "/account",
            {"account_type": "student", "username": username},
            content_type="application/json",
            **bearer(token(username="")),
        )

        assert response.status_code == 422
        [detail] = response.json()["error"]["details"]
        assert detail["field"] == "body.username"

    def test_refuses_a_username_someone_has_in_any_case(self, client: Any, token: Token) -> None:
        client.get("/account", **bearer(token(sub="auth0|first", username="Ada")))

        response = client.post(
            "/account",
            {"account_type": "student", "username": "ada"},
            content_type="application/json",
            **bearer(token(sub="auth0|second", email="bea@nyu.edu", username="")),
        )

        assert response.status_code == 422
        assert response.json()["error"]["details"][0]["type"] == "username_taken"

    def test_will_not_rename_an_auth0_username(self, client: Any, token: Token) -> None:
        response = client.post(
            "/account",
            {"account_type": "student", "username": "someone_else"},
            content_type="application/json",
            **bearer(token(username="ada")),
        )

        assert response.status_code == 422
        assert Account.objects.get().account_type == ""

    def test_makes_a_business_account(self, client: Any, token: Token) -> None:
        response = client.post(
            "/account",
            {"account_type": "business", "business_name": "  Grumpy Coffee  "},
            content_type="application/json",
            **bearer(token(sub="auth0|owner", email="owner@grumpy.com", username="")),
        )

        assert response.status_code == 201
        body = response.json()
        assert body["account_type"] == "business"
        assert body["business_name"] == "Grumpy Coffee"

    def test_refuses_a_business_without_a_name(self, client: Any, token: Token) -> None:
        response = client.post(
            "/account",
            {"account_type": "business", "business_name": "   "},
            content_type="application/json",
            **bearer(token(email="owner@grumpy.com")),
        )

        assert response.status_code == 422
        assert response.json()["error"]["details"][0]["field"] == "body.business_name"

    def test_refuses_an_unknown_account_type(self, client: Any, token: Token) -> None:
        response = client.post(
            "/account",
            {"account_type": "admin"},
            content_type="application/json",
            **bearer(token()),
        )

        assert response.status_code == 422
        assert response.json()["error"]["details"][0]["field"] == "body.account_type"

    def test_happens_only_once(self, client: Any, token: Token) -> None:
        client.post(
            "/account",
            {"account_type": "student"},
            content_type="application/json",
            **bearer(token()),
        )

        response = client.post(
            "/account",
            {"account_type": "business", "business_name": "Switcheroo"},
            content_type="application/json",
            **bearer(token()),
        )

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "conflict"
        assert Account.objects.get().account_type == AccountType.STUDENT

    def test_needs_a_token(self, client: Any) -> None:
        response = client.post(
            "/account", {"account_type": "student"}, content_type="application/json"
        )

        assert response.status_code == 401


@pytest.fixture
def id_token(signing_key: rsa.RSAPrivateKey) -> Token:
    """Sign an ID token, as Auth0 issues to the single-page application."""

    def sign(
        sub: str = "auth0|student",
        email: str = "ada@nyu.edu",
        email_verified: bool = True,
        key: rsa.RSAPrivateKey | None = None,
        **overrides: Any,
    ) -> str:
        now = int(time.time())
        claims = {
            "iss": f"https://{DOMAIN}/",
            "aud": "spa-client-id",
            "sub": sub,
            "iat": now,
            "exp": now + 3600,
            "email": email,
            "email_verified": email_verified,
            **overrides,
        }
        return jwt.encode(claims, key or signing_key, algorithm="RS256", headers={"kid": KID})

    return sign


def with_id_token(access: str, identity: str) -> dict[str, str]:
    return {**bearer(access), "HTTP_X_ID_TOKEN": identity}


@pytest.mark.django_db
class TestEmailFromIdToken:
    """Without the optional Auth0 Action, the email comes from the ID token."""

    def test_reads_the_email_and_its_verification(
        self, client: Any, token: Token, id_token: Token
    ) -> None:
        access = token(email="", email_verified=False, username="")

        body = client.get("/account", **with_id_token(access, id_token())).json()

        assert body["email"] == "ada@nyu.edu"
        assert body["email_verified"] is True

    def test_lets_a_student_finish_sign_up(
        self, client: Any, token: Token, id_token: Token
    ) -> None:
        access = token(email="", email_verified=False, username="")

        response = client.post(
            "/account",
            {"account_type": "student", "username": "ada_l"},
            content_type="application/json",
            **with_id_token(access, id_token()),
        )

        assert response.status_code == 201

    def test_ignores_an_id_token_for_someone_else(
        self, client: Any, token: Token, id_token: Token
    ) -> None:
        access = token(email="", email_verified=False, username="")

        body = client.get(
            "/account", **with_id_token(access, id_token(sub="auth0|someone-else"))
        ).json()

        assert body["email"] == ""
        assert body["email_verified"] is False

    def test_ignores_a_forged_id_token(self, client: Any, token: Token, id_token: Token) -> None:
        access = token(email="", email_verified=False, username="")

        response = client.get("/account", **with_id_token(access, id_token(key=rsa_key())))

        # The access token is still good, so the request is; the forgery just
        # counts for nothing.
        assert response.status_code == 200
        assert response.json()["email_verified"] is False

    def test_ignores_an_id_token_issued_to_another_application(
        self, client: Any, token: Token, id_token: Token
    ) -> None:
        access = token(email="", email_verified=False, username="")

        body = client.get("/account", **with_id_token(access, id_token(aud="another-app"))).json()

        assert body["email_verified"] is False

    def test_ignores_an_expired_id_token(self, client: Any, token: Token, id_token: Token) -> None:
        access = token(email="", email_verified=False, username="")
        past = int(time.time()) - 7200

        body = client.get(
            "/account", **with_id_token(access, id_token(iat=past, exp=past + 60))
        ).json()

        assert body["email_verified"] is False

    def test_keeps_the_email_when_a_request_carries_none(
        self, client: Any, token: Token, id_token: Token
    ) -> None:
        access = token(email="", email_verified=False, username="")
        client.get("/account", **with_id_token(access, id_token()))

        body = client.get("/account", **bearer(access)).json()

        assert body["email"] == "ada@nyu.edu"
        assert body["email_verified"] is True

    def test_prefers_the_action_claims_when_present(
        self, client: Any, token: Token, id_token: Token
    ) -> None:
        access = token(email="ada@nyu.edu", email_verified=True)

        body = client.get(
            "/account", **with_id_token(access, id_token(email="other@nyu.edu"))
        ).json()

        assert body["email"] == "ada@nyu.edu"


@pytest.mark.django_db
class TestUsernameAvailability:
    def test_says_a_free_name_is_available(self, client: Any) -> None:
        body = client.get("/usernames/grace_h").json()

        assert body == {"username": "grace_h", "available": True, "reason": None, "message": None}

    def test_says_a_taken_name_is_not_in_any_case(self, client: Any, token: Token) -> None:
        client.get("/account", **bearer(token(username="Ada")))

        body = client.get("/usernames/ada").json()

        assert body["available"] is False
        assert body["reason"] == "username_taken"

    def test_explains_a_malformed_name(self, client: Any) -> None:
        body = client.get("/usernames/ab").json()

        assert body["available"] is False
        assert body["reason"] == "invalid_username"

    def test_needs_no_token(self, client: Any) -> None:
        assert client.get("/usernames/anyone").status_code == 200
