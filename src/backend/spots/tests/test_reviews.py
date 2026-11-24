"""Tests for students reviewing study spots.

Authentication is forced rather than signed, as in ``test_listings``: the Auth0
token check has its own tests, and what matters here is who may write a review
and what the database will accept.
"""

from __future__ import annotations

from typing import Any

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from rest_framework.test import APIClient

from accounts.models import Account, AccountType
from spots.models import MAX_REVIEW_BODY, Review, StudySpot

pytestmark = pytest.mark.django_db

REVIEW: dict[str, Any] = {
    "rating": 4,
    "noise": 5,
    "wifi": 3,
    "seating": 2,
    "outlets": 1,
    "body": "Quiet upstairs, few outlets.",
}


def account(subject: str, account_type: str = AccountType.STUDENT, username: str = "") -> Account:
    user = get_user_model().objects.create(username=subject)
    return Account.objects.create(
        user=user,
        account_type=account_type,
        business_name=subject if account_type == AccountType.BUSINESS else "",
        email=f"{subject.replace('|', '.')}@example.com",
        username=username,
    )


def spot(spot_id: str) -> StudySpot:
    return StudySpot.objects.create(
        id=spot_id,
        name=spot_id,
        category="public_library",
        borough="Manhattan",
        latitude=40.73,
        longitude=-73.99,
    )


def client_for(author: Account | None) -> APIClient:
    client = APIClient()
    if author is not None:
        client.force_authenticate(user=author.user)
    return client


def reviews_url(spot_id: str) -> str:
    return f"/spots/{spot_id}/reviews"


@pytest.fixture
def library() -> StudySpot:
    return spot("facdb:library")


@pytest.fixture
def student() -> Account:
    return account("auth0|student", username="ada")


class TestCreating:
    def test_a_student_reviews_a_spot(self, student: Account, library: StudySpot) -> None:
        response = client_for(student).post(reviews_url(library.pk), REVIEW, format="json")

        assert response.status_code == 201
        body = response.json()
        assert {name: body[name] for name in REVIEW} == REVIEW
        assert body["spot"] == library.pk
        assert body["author"] == {"username": "ada"}
        assert body["reply"] is None
        review = Review.objects.get(pk=body["id"])
        assert (review.spot, review.author) == (library, student)

    def test_only_the_overall_rating_is_required(
        self, student: Account, library: StudySpot
    ) -> None:
        response = client_for(student).post(reviews_url(library.pk), {"rating": 3}, format="json")

        assert response.status_code == 201
        body = response.json()
        assert body["rating"] == 3
        assert [body[name] for name in ("noise", "wifi", "seating", "outlets")] == [None] * 4
        assert body["body"] == ""

    def test_an_anonymous_caller_cannot(self, library: StudySpot) -> None:
        response = client_for(None).post(reviews_url(library.pk), REVIEW, format="json")

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "unauthorized"
        assert not Review.objects.exists()

    @pytest.mark.parametrize("account_type", [AccountType.BUSINESS, ""])
    def test_only_a_student_account_can(self, library: StudySpot, account_type: str) -> None:
        caller = account("auth0|other", account_type)

        response = client_for(caller).post(reviews_url(library.pk), REVIEW, format="json")

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "forbidden"
        assert not Review.objects.exists()

    def test_a_second_review_of_the_same_spot_conflicts(
        self, student: Account, library: StudySpot
    ) -> None:
        client = client_for(student)
        assert client.post(reviews_url(library.pk), REVIEW, format="json").status_code == 201

        response = client.post(reviews_url(library.pk), {"rating": 1}, format="json")

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "conflict"
        assert Review.objects.get().rating == REVIEW["rating"]

    def test_one_student_reviews_many_spots_and_many_students_one_spot(
        self, student: Account, library: StudySpot
    ) -> None:
        cafe = spot("dohmh:cafe")
        classmate = account("auth0|classmate")

        for author, place in [(student, library), (student, cafe), (classmate, library)]:
            response = client_for(author).post(reviews_url(place.pk), REVIEW, format="json")
            assert response.status_code == 201

        assert Review.objects.count() == 3

    def test_an_unknown_spot_is_not_found(self, student: Account) -> None:
        response = client_for(student).post(reviews_url("facdb:missing"), REVIEW, format="json")

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"
        assert not Review.objects.exists()

    @pytest.mark.parametrize(
        "change",
        [
            {"rating": None},
            {"rating": 0},
            {"rating": 6},
            {"rating": 3.5},
            {"rating": "abc"},
            {"noise": 0},
            {"wifi": 6},
            {"body": "x" * (MAX_REVIEW_BODY + 1)},
            {"author": 1},
            {"spot": "dohmh:cafe"},
            {"created_at": "2020-01-01T00:00:00Z"},
        ],
    )
    def test_rejects_an_invalid_body(
        self, student: Account, library: StudySpot, change: dict[str, Any]
    ) -> None:
        response = client_for(student).post(
            reviews_url(library.pk), {**REVIEW, **change}, format="json"
        )

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"
        assert not Review.objects.exists()

    def test_rejects_a_missing_rating(self, student: Account, library: StudySpot) -> None:
        without_rating = {name: value for name, value in REVIEW.items() if name != "rating"}

        response = client_for(student).post(reviews_url(library.pk), without_rating, format="json")

        assert response.status_code == 422
        assert response.json()["error"]["details"][0]["field"] == "body.rating"
        assert not Review.objects.exists()

    def test_accepts_a_body_of_exactly_the_limit(
        self, student: Account, library: StudySpot
    ) -> None:
        text = "x" * MAX_REVIEW_BODY

        response = client_for(student).post(
            reviews_url(library.pk), {"rating": 5, "body": text}, format="json"
        )

        assert response.status_code == 201
        assert Review.objects.get().body == text


class TestReading:
    def write(self, author: Account, place: StudySpot, rating: int = 4) -> Review:
        return Review.objects.create(spot=place, author=author, rating=rating)

    def test_newest_first_with_id_breaking_ties(self, library: StudySpot) -> None:
        older, newer, newest = (self.write(account(f"auth0|{n}"), library) for n in ("a", "b", "c"))
        # Same instant for two of them: the higher id comes first.
        Review.objects.filter(pk=newer.pk).update(created_at=newest.created_at)

        body = APIClient().get(reviews_url(library.pk)).json()

        assert [item["id"] for item in body["items"]] == [newest.pk, newer.pk, older.pk]

    def test_pages_like_spots(self, library: StudySpot) -> None:
        for n in range(3):
            self.write(account(f"auth0|{n}"), library)

        first = APIClient().get(reviews_url(library.pk), {"limit": 2}).json()
        last = APIClient().get(reviews_url(library.pk), {"limit": 2, "offset": 2}).json()

        assert first["pagination"] == {
            "limit": 2,
            "offset": 0,
            "count": 2,
            "total": 3,
            "has_more": True,
        }
        assert last["pagination"] == {
            "limit": 2,
            "offset": 2,
            "count": 1,
            "total": 3,
            "has_more": False,
        }
        ids = [item["id"] for item in first["items"] + last["items"]]
        assert sorted(ids) == sorted(Review.objects.values_list("pk", flat=True))

    def test_a_spot_without_reviews_has_an_empty_page(self, library: StudySpot) -> None:
        response = APIClient().get(reviews_url(library.pk))

        assert response.status_code == 200
        assert response.json() == {
            "items": [],
            "pagination": {"limit": 20, "offset": 0, "count": 0, "total": 0, "has_more": False},
            "summary": {"average_rating": None},
        }

    def test_only_this_spots_reviews(self, student: Account, library: StudySpot) -> None:
        mine = self.write(student, library)
        self.write(student, spot("dohmh:cafe"))

        items = APIClient().get(reviews_url(library.pk)).json()["items"]

        assert [item["id"] for item in items] == [mine.pk]

    def test_the_author_is_a_username_and_never_an_email(self, library: StudySpot) -> None:
        self.write(account("auth0|named", username="ada"), library)
        self.write(account("auth0|unnamed"), library)

        response = APIClient().get(reviews_url(library.pk))

        authors = [item["author"] for item in response.json()["items"]]
        assert sorted(authors, key=lambda a: a["username"] or "") == [
            {"username": None},
            {"username": "ada"},
        ]
        assert "example.com" not in response.content.decode()

    @pytest.mark.parametrize(
        "query", [{"limit": 0}, {"limit": 101}, {"offset": -1}, {"sort": "rating"}]
    )
    def test_rejects_a_bad_query(self, library: StudySpot, query: dict[str, Any]) -> None:
        response = APIClient().get(reviews_url(library.pk), query)

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"

    def test_an_unknown_spot_is_not_found(self) -> None:
        response = APIClient().get(reviews_url("facdb:missing"))

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"


class TestDatabaseConstraints:
    """What the database refuses even when a write skips the serializer."""

    def test_one_review_per_author_and_spot(self, student: Account, library: StudySpot) -> None:
        Review.objects.create(spot=library, author=student, rating=4)

        with pytest.raises(IntegrityError), transaction.atomic():
            Review.objects.create(spot=library, author=student, rating=2)

        assert Review.objects.count() == 1

    @pytest.mark.parametrize(
        "scores",
        [
            {"rating": 0},
            {"rating": 6},
            {"rating": 3, "noise": 0},
            {"rating": 3, "wifi": 6},
            {"rating": 3, "seating": -1},
            {"rating": 3, "outlets": 9},
        ],
    )
    def test_scores_stay_between_one_and_five(
        self, student: Account, library: StudySpot, scores: dict[str, int]
    ) -> None:
        with pytest.raises(IntegrityError), transaction.atomic():
            Review.objects.create(spot=library, author=student, **scores)

        assert not Review.objects.exists()
