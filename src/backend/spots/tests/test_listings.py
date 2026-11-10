"""Tests for a business owner managing their own listings.

Authentication is forced rather than signed: the Auth0 token check has its own
tests in ``accounts/tests``, and what matters here is who may change which spot.
"""

from __future__ import annotations

from typing import Any

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from accounts.models import Account, AccountType
from spots.models import StudySpot

pytestmark = pytest.mark.django_db

LISTING: dict[str, Any] = {
    "name": "Quiet Corner Cafe",
    "category": "cafe",
    "address": "12 Bleecker Street, New York, NY 10012",
    "borough": "manhattan",
    "latitude": 40.7259,
    "longitude": -73.9946,
    "opening_hours": "Mo-Fr 08:00-18:00",
}


def account(subject: str, account_type: str = AccountType.BUSINESS) -> Account:
    user = get_user_model().objects.create(username=subject)
    return Account.objects.create(
        user=user,
        account_type=account_type,
        business_name=subject if account_type == AccountType.BUSINESS else "",
    )


def client_for(owner: Account | None) -> APIClient:
    client = APIClient()
    if owner is not None:
        client.force_authenticate(user=owner.user)
    return client


@pytest.fixture
def owner() -> Account:
    return account("auth0|owner")


@pytest.fixture
def listing(owner: Account) -> StudySpot:
    response = client_for(owner).post("/listings", LISTING, format="json")
    assert response.status_code == 201
    return StudySpot.objects.get(pk=response.json()["id"])


class TestCreating:
    def test_a_business_creates_a_public_listing(self, owner: Account) -> None:
        response = client_for(owner).post("/listings", LISTING, format="json")

        assert response.status_code == 201
        body = response.json()
        assert body["id"].startswith("listing:")
        assert body["borough"] == "Manhattan"
        assert StudySpot.objects.get(pk=body["id"]).owner == owner
        # Readable by anyone through the public route, in the public shape.
        assert APIClient().get(f"/spots/{body['id']}").json() == body

    def test_a_student_cannot(self) -> None:
        student = account("auth0|student", AccountType.STUDENT)

        response = client_for(student).post("/listings", LISTING, format="json")

        assert response.status_code == 403
        assert not StudySpot.objects.exists()

    def test_an_anonymous_caller_cannot(self) -> None:
        assert client_for(None).post("/listings", LISTING, format="json").status_code == 401

    @pytest.mark.parametrize(
        "change",
        [
            {"id": "facdb:bobst"},
            {"subway_station": "Bleecker St"},
            {"latitude": 91},
            {"borough": "Hoboken"},
            {"category": "coffee shop"},
            {"category": "public_library"},
            {"address": ""},
        ],
    )
    def test_rejects_what_an_owner_cannot_set(self, owner: Account, change: dict) -> None:
        response = client_for(owner).post("/listings", {**LISTING, **change}, format="json")

        assert response.status_code == 422
        assert not StudySpot.objects.exists()


class TestOwnership:
    def test_lists_only_the_callers_listings(self, owner: Account, listing: StudySpot) -> None:
        other = account("auth0|other")

        assert [item["id"] for item in client_for(owner).get("/listings").json()["items"]] == [
            listing.pk
        ]
        assert client_for(other).get("/listings").json()["items"] == []

    def test_the_owner_updates_their_listing(self, owner: Account, listing: StudySpot) -> None:
        response = client_for(owner).patch(
            f"/listings/{listing.pk}", {"name": "Louder Corner Cafe"}, format="json"
        )

        assert response.status_code == 200
        assert response.json()["name"] == "Louder Corner Cafe"
        listing.refresh_from_db()
        assert listing.name == "Louder Corner Cafe"
        assert listing.address == LISTING["address"]

    def test_the_owner_deletes_their_listing(self, owner: Account, listing: StudySpot) -> None:
        response = client_for(owner).delete(f"/listings/{listing.pk}")

        assert response.status_code == 204
        assert not StudySpot.objects.filter(pk=listing.pk).exists()

    def test_another_business_cannot_touch_it(self, listing: StudySpot) -> None:
        other = client_for(account("auth0|other"))

        patched = other.patch(f"/listings/{listing.pk}", {"name": "Mine now"}, format="json")
        deleted = other.delete(f"/listings/{listing.pk}")

        assert patched.status_code == 404
        assert deleted.status_code == 404
        listing.refresh_from_db()
        assert listing.name == LISTING["name"]

    def test_an_imported_spot_is_nobodys_listing(self, owner: Account) -> None:
        imported = StudySpot.objects.create(
            id="facdb:bobst",
            name="Bobst Library",
            category="academic_library",
            borough="Manhattan",
            latitude=40.7295,
            longitude=-73.9973,
        )

        assert client_for(owner).delete(f"/listings/{imported.pk}").status_code == 404
        assert StudySpot.objects.filter(pk=imported.pk).exists()
