from __future__ import annotations

import time
from datetime import timedelta
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from django.contrib.auth import get_user_model
from django.db import IntegrityError, OperationalError, connection, transaction
from django.utils import timezone

from accounts.models import Account, AccountType, Favourite
from spots.models import StudySpot
from spots.tests.test_spots_api import CONTRACT_FIELDS, RECORDS

from .test_accounts_api import AUDIENCE, DOMAIN, KID, NAMESPACE, Token, bearer, jwks, rsa_key

pytestmark = pytest.mark.django_db

OPERATIONS = [
    ("get", "/favourites"),
    ("put", "/favourites/facdb:bobst"),
    ("delete", "/favourites/facdb:bobst"),
]


@pytest.fixture(scope="module")
def signing_key() -> rsa.RSAPrivateKey:
    return rsa_key()


@pytest.fixture(autouse=True)
def auth0(settings: Any, signing_key: rsa.RSAPrivateKey) -> None:
    settings.ACCOUNTS_ENABLED = True
    settings.AUTH0_DOMAIN = DOMAIN
    settings.AUTH0_CLIENT_ID = "spa-client-id"
    settings.AUTH0_AUDIENCE = AUDIENCE
    settings.AUTH0_JWKS = jwks(signing_key)
    settings.AUTH0_CLAIM_NAMESPACE = NAMESPACE


@pytest.fixture
def token(signing_key: rsa.RSAPrivateKey) -> Token:
    def sign(
        sub: str = "auth0|student",
        key: rsa.RSAPrivateKey | None = None,
        **overrides: Any,
    ) -> str:
        now = int(time.time())
        return jwt.encode(
            {
                "iss": f"https://{DOMAIN}/",
                "aud": AUDIENCE,
                "sub": sub,
                "iat": now,
                "exp": now + 3600,
                f"{NAMESPACE}email": "ada@nyu.edu",
                f"{NAMESPACE}email_verified": True,
                f"{NAMESPACE}username": "ada",
                **overrides,
            },
            key or signing_key,
            algorithm="RS256",
            headers={"kid": KID},
        )

    return sign


def create_account(subject: str, account_type: str = AccountType.STUDENT) -> Account:
    return Account.objects.create(
        user=get_user_model().objects.create(username=subject),
        account_type=account_type,
        username=subject.split("|")[-1],
        business_name="A business" if account_type == AccountType.BUSINESS else "",
    )


@pytest.fixture
def student() -> Account:
    return create_account("auth0|student")


@pytest.fixture
def spots() -> list[StudySpot]:
    return StudySpot.objects.bulk_create(StudySpot(**record) for record in RECORDS)


def assert_private(response: Any) -> None:
    directives = {part.strip() for part in response["Cache-Control"].split(",")}
    assert {"private", "no-store"} <= directives


@pytest.mark.parametrize(("method", "path"), OPERATIONS)
def test_database_outage_keeps_favourite_errors_private(
    client: Any, token: Token, method: str, path: str
) -> None:
    def unavailable(*args: Any, **kwargs: Any) -> None:
        raise OperationalError("Database unavailable")

    with connection.execute_wrapper(unavailable):
        response = getattr(client, method)(path, **bearer(token()))

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "database_unavailable"
    assert_private(response)


class TestFavouritesGate:
    @pytest.mark.parametrize(("method", "path"), OPERATIONS)
    @pytest.mark.parametrize("credential", ["missing", "malformed", "wrong_key", "expired"])
    def test_requires_a_verified_access_token(
        self, client: Any, token: Token, method: str, path: str, credential: str
    ) -> None:
        headers = {}
        if credential == "malformed":
            headers = bearer("not-a-token")
        elif credential == "wrong_key":
            headers = bearer(token(key=rsa_key()))
        elif credential == "expired":
            headers = bearer(token(iat=1, exp=2))
        response = getattr(client, method)(path, **headers)

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "unauthorized"
        assert response["WWW-Authenticate"].startswith("Bearer")
        assert_private(response)
        assert not Favourite.objects.exists()

    @pytest.mark.parametrize(("method", "path"), OPERATIONS)
    def test_does_not_accept_a_django_session(
        self, client: Any, student: Account, method: str, path: str
    ) -> None:
        client.force_login(student.user)
        response = getattr(client, method)(path)

        assert response.status_code == 401
        assert_private(response)

    @pytest.mark.parametrize(
        ("disabled_setting", "disabled_value"),
        [("ACCOUNTS_ENABLED", False), ("AUTH0_AUDIENCE", "")],
    )
    @pytest.mark.parametrize(("method", "path"), OPERATIONS)
    def test_rejects_tokens_when_auth_is_disabled(
        self,
        client: Any,
        settings: Any,
        token: Token,
        method: str,
        path: str,
        disabled_setting: str,
        disabled_value: Any,
    ) -> None:
        setattr(settings, disabled_setting, disabled_value)
        response = getattr(client, method)(path, **bearer(token()))

        assert response.status_code == 401
        assert_private(response)

    @pytest.mark.parametrize(("method", "path"), OPERATIONS)
    @pytest.mark.parametrize("account_type", ["", AccountType.BUSINESS])
    def test_eligibility_precedes_query_validation_and_spot_lookup(
        self,
        client: Any,
        token: Token,
        method: str,
        path: str,
        account_type: str,
    ) -> None:
        create_account("auth0|student", account_type)
        access_token = token(**{f"{NAMESPACE}account_type": "student"})
        response = getattr(client, method)(path + "?unknown=1", **bearer(access_token))

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "conflict"
        assert_private(response)
        assert not Favourite.objects.exists()
        assert not StudySpot.objects.exists()

    @pytest.mark.parametrize(("method", "path"), OPERATIONS)
    def test_does_not_infer_completion_from_token_profile(
        self, client: Any, token: Token, method: str, path: str
    ) -> None:
        response = getattr(client, method)(path, **bearer(token()))

        assert response.status_code == 409
        assert Account.objects.get().account_type == ""
        assert_private(response)

    @pytest.mark.parametrize(("method", "path"), OPERATIONS)
    def test_rechecks_the_persisted_account_type_on_every_operation(
        self,
        client: Any,
        token: Token,
        student: Account,
        spots: list[StudySpot],
        method: str,
        path: str,
    ) -> None:
        Favourite.objects.create(account=student, spot=spots[0])
        Account.objects.filter(pk=student.pk).update(account_type="")
        response = getattr(client, method)(path, **bearer(token()))

        assert response.status_code == 409
        assert Favourite.objects.filter(account=student, spot=spots[0]).exists()
        assert_private(response)


class TestFavouritesOwnership:
    def test_client_supplied_ownership_cannot_save_or_remove_for_someone_else(
        self, client: Any, token: Token, student: Account, spots: list[StudySpot]
    ) -> None:
        other = create_account("auth0|other")
        path = f"/favourites/{spots[0].pk}"
        body = {"account": other.pk, "account_id": other.pk, "user_id": other.user_id}
        saved = client.put(path, body, content_type="application/json", **bearer(token()))

        assert saved.status_code == 204
        assert saved.content == b""
        assert list(Favourite.objects.values_list("account_id", flat=True)) == [student.pk]
        assert_private(saved)

        other_token = token(sub="auth0|other", **{f"{NAMESPACE}username": "other"})
        assert client.get("/favourites", **bearer(other_token)).json()["items"] == []
        removed = client.delete(path, body, content_type="application/json", **bearer(other_token))
        assert removed.status_code == 204
        assert Favourite.objects.filter(account=student, spot=spots[0]).exists()

        assert client.put(path, **bearer(other_token)).status_code == 204
        assert Favourite.objects.filter(spot=spots[0]).count() == 2
        assert client.delete(path, **bearer(token())).status_code == 204
        assert list(Favourite.objects.values_list("account_id", flat=True)) == [other.pk]
        assert client.get("/favourites", **bearer(token())).json()["items"] == []
        assert (
            client.get("/favourites", **bearer(other_token)).json()["items"][0]["id"] == spots[0].pk
        )

    def test_access_subject_remains_owner_when_profile_changes(
        self, client: Any, token: Token, student: Account, spots: list[StudySpot]
    ) -> None:
        Favourite.objects.create(account=student, spot=spots[0])
        changed = token(
            **{
                f"{NAMESPACE}email": "different@example.com",
                f"{NAMESPACE}email_verified": False,
                f"{NAMESPACE}username": "changed_name",
            }
        )
        body = client.get("/favourites", **bearer(changed)).json()

        assert [spot["id"] for spot in body["items"]] == [spots[0].pk]
        assert Favourite.objects.get().account_id == student.pk

    def test_an_account_query_parameter_cannot_select_another_collection(
        self, client: Any, token: Token, student: Account, spots: list[StudySpot]
    ) -> None:
        other = create_account("auth0|other")
        Favourite.objects.create(account=other, spot=spots[0])
        response = client.get(f"/favourites?account_id={other.pk}", **bearer(token()))

        assert response.status_code == 422
        assert response.json()["error"]["details"][0]["field"] == "query.account_id"
        assert_private(response)


class TestFavouritesMutation:
    def test_repeated_saves_preserve_the_relationship_and_saved_time(
        self, client: Any, token: Token, student: Account, spots: list[StudySpot]
    ) -> None:
        path = f"/favourites/{spots[0].pk}"
        assert client.put(path, **bearer(token())).status_code == 204
        saved = Favourite.objects.get()
        for _ in range(3):
            response = client.put(path, **bearer(token()))
            assert response.status_code == 204
            assert response.content == b""
            assert_private(response)

        current = Favourite.objects.get()
        assert current.pk == saved.pk
        assert current.created_at == saved.created_at

    def test_removals_converge_even_when_the_spot_no_longer_exists(
        self, client: Any, token: Token, student: Account, spots: list[StudySpot]
    ) -> None:
        path = f"/favourites/{spots[0].pk}"
        Favourite.objects.create(account=student, spot=spots[0])
        for _ in range(2):
            response = client.delete(path, **bearer(token()))
            assert response.status_code == 204
            assert response.content == b""
            assert_private(response)
        spots[0].delete()
        assert client.delete(path, **bearer(token())).status_code == 204
        assert not Favourite.objects.exists()

    def test_saving_an_absent_spot_is_not_found(
        self, client: Any, token: Token, student: Account
    ) -> None:
        response = client.put("/favourites/facdb:absent", **bearer(token()))

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"
        assert_private(response)
        assert not Favourite.objects.exists()

    def test_the_database_refuses_duplicate_relationships(
        self, student: Account, spots: list[StudySpot]
    ) -> None:
        Favourite.objects.create(account=student, spot=spots[0])
        with pytest.raises(IntegrityError), transaction.atomic():
            Favourite.objects.create(account=student, spot=spots[0])
        assert Favourite.objects.filter(account=student, spot=spots[0]).count() == 1

    def test_removing_an_account_cascades_only_its_favourites(
        self, student: Account, spots: list[StudySpot]
    ) -> None:
        other = create_account("auth0|other")
        Favourite.objects.create(account=student, spot=spots[0])
        kept = Favourite.objects.create(account=other, spot=spots[0])
        student.delete()

        assert list(Favourite.objects.values_list("pk", flat=True)) == [kept.pk]
        assert StudySpot.objects.filter(pk=spots[0].pk).exists()


class TestFavouritesList:
    def test_empty_collection_uses_the_spot_page_contract(
        self, client: Any, token: Token, student: Account
    ) -> None:
        response = client.get("/favourites", **bearer(token()))

        assert response.status_code == 200
        assert response.json() == {
            "items": [],
            "pagination": {"limit": 20, "offset": 0, "count": 0, "total": 0, "has_more": False},
        }
        assert_private(response)

    def test_items_are_live_spot_values_without_private_metadata(
        self, client: Any, token: Token, student: Account, spots: list[StudySpot]
    ) -> None:
        Favourite.objects.create(account=student, spot=spots[0])
        StudySpot.objects.filter(pk=spots[0].pk).update(
            name="A refreshed library", venue_wifi=False
        )
        response = client.get("/favourites", **bearer(token()))
        [item] = response.json()["items"]

        assert set(item) == CONTRACT_FIELDS
        assert item["name"] == "A refreshed library"
        assert item["venue_wifi"] is False
        assert item == client.get(f"/spots/{spots[0].pk}").json()
        assert_private(response)

    def test_newest_order_has_a_total_tiebreaker_and_stable_pages(
        self, client: Any, token: Token, student: Account, spots: list[StudySpot]
    ) -> None:
        saved = [Favourite.objects.create(account=student, spot=spot) for spot in spots]
        now = timezone.now()
        Favourite.objects.filter(pk__in=[row.pk for row in saved]).update(created_at=now)
        Favourite.objects.filter(pk=saved[0].pk).update(created_at=now + timedelta(days=1))
        expected = [spots[0].pk, *[spot.pk for spot in reversed(spots[1:])]]
        seen = []
        for offset in range(0, len(spots), 2):
            response = client.get(f"/favourites?limit=2&offset={offset}", **bearer(token()))
            body = response.json()
            seen.extend(item["id"] for item in body["items"])
            assert body["pagination"] == {
                "limit": 2,
                "offset": offset,
                "count": min(2, len(spots) - offset),
                "total": len(spots),
                "has_more": offset + 2 < len(spots),
            }
        assert seen == expected
        assert len(set(seen)) == len(spots)
        again = client.get("/favourites?limit=100", **bearer(token())).json()
        assert [item["id"] for item in again["items"]] == expected
        assert again["pagination"]["limit"] == 100

    def test_offset_after_the_end_keeps_the_collection_total(
        self, client: Any, token: Token, student: Account, spots: list[StudySpot]
    ) -> None:
        Favourite.objects.create(account=student, spot=spots[0])
        body = client.get("/favourites?offset=100", **bearer(token())).json()

        assert body["items"] == []
        assert body["pagination"] == {
            "limit": 20,
            "offset": 100,
            "count": 0,
            "total": 1,
            "has_more": False,
        }

    @pytest.mark.parametrize(
        ("query", "field"),
        [
            ("limit=0", "limit"),
            ("limit=101", "limit"),
            ("limit=-1", "limit"),
            ("limit=1.5", "limit"),
            ("limit=abc", "limit"),
            ("limit=", "limit"),
            ("offset=-1", "offset"),
            ("offset=1.5", "offset"),
            ("offset=abc", "offset"),
            ("offset=", "offset"),
            ("name=Library", "name"),
        ],
    )
    def test_rejects_invalid_or_unknown_pagination(
        self, client: Any, token: Token, student: Account, query: str, field: str
    ) -> None:
        response = client.get(f"/favourites?{query}", **bearer(token()))

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"
        assert response.json()["error"]["details"][0]["field"] == f"query.{field}"
        assert_private(response)
