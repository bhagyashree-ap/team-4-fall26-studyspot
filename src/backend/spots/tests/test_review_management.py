from __future__ import annotations

from typing import Any

import pytest
from rest_framework.test import APIClient

from accounts.models import Account, AccountType
from spots.models import MAX_REVIEW_BODY, Review, ReviewReply, StudySpot

from . import test_reviews as api
from .test_reviews import REVIEW, account, client_for, reviews_url, spot

pytestmark = pytest.mark.django_db
student = api.student
library = api.library


@pytest.fixture
def owner() -> Account:
    return account("auth0|owner", AccountType.BUSINESS)


@pytest.fixture
def listing(owner: Account) -> StudySpot:
    return StudySpot.objects.create(
        id="listing:cafe",
        name="Campus Cafe",
        owner=owner,
        category="cafe",
        borough="Manhattan",
        latitude=40.73,
        longitude=-73.99,
    )


class TestViewer:
    def test_own_review_is_available_outside_the_first_page(
        self, student: Account, library: StudySpot
    ) -> None:
        mine = Review.objects.create(spot=library, author=student, **REVIEW)
        reply = ReviewReply.objects.create(review=mine, body="Thank you for visiting.")
        for index in range(21):
            Review.objects.create(spot=library, author=account(f"auth0|newer-{index}"), rating=3)

        first_page = APIClient().get(reviews_url(library.pk)).json()
        assert mine.pk not in [review["id"] for review in first_page["items"]]
        assert first_page["pagination"]["has_more"] is True

        response = client_for(student).get(f"{reviews_url(library.pk)}/viewer")
        assert response.status_code == 200
        body = response.json()
        assert set(body) == {"kind", "own_review"}
        assert body["kind"] == "student"
        assert body["own_review"]["id"] == mine.pk
        assert body["own_review"]["reply"]["body"] == reply.body
        assert {name: body["own_review"][name] for name in REVIEW} == REVIEW
        client = client_for(student)
        edited = client.patch(f"{reviews_url(library.pk)}/mine", {"rating": 5}, format="json")
        assert edited.status_code == 200
        assert edited.json()["id"] == mine.pk
        assert edited.json()["rating"] == 5
        assert edited.json()["reply"] == body["own_review"]["reply"]
        assert client.get(f"{reviews_url(library.pk)}/viewer").json()["own_review"] == (
            edited.json()
        )
        assert client.delete(f"{reviews_url(library.pk)}/mine").status_code == 204
        assert client.get(f"{reviews_url(library.pk)}/viewer").json() == {
            "kind": "student",
            "own_review": None,
        }
        assert APIClient().get(reviews_url(library.pk)).json()["pagination"]["total"] == 21
        assert not ReviewReply.objects.filter(pk=reply.pk).exists()

    def test_student_without_review_and_student_isolation(
        self, student: Account, library: StudySpot
    ) -> None:
        Review.objects.create(spot=library, author=student, rating=4)
        stranger = account("auth0|stranger")

        response = client_for(stranger).get(f"{reviews_url(library.pk)}/viewer")

        assert response.status_code == 200
        assert response.json() == {"kind": "student", "own_review": None}

    def test_owner_and_other_reader_roles(
        self, owner: Account, listing: StudySpot, library: StudySpot
    ) -> None:
        for caller, place, kind in [
            (owner, listing, "owner"),
            (owner, library, "reader"),
            (account("auth0|other-business", AccountType.BUSINESS), listing, "reader"),
            (account("auth0|unfinished", ""), listing, "reader"),
        ]:
            response = client_for(caller).get(f"{reviews_url(place.pk)}/viewer")

            assert response.status_code == 200
            assert response.json() == {"kind": kind}

    @pytest.mark.parametrize(
        "signed_in,exists,expected", [(True, True, 200), (True, False, 404), (False, True, 401)]
    )
    def test_private_no_store_including_errors(
        self,
        student: Account,
        library: StudySpot,
        signed_in: bool,
        exists: bool,
        expected: int,
    ) -> None:
        place_id = library.pk if exists else "facdb:missing"
        response = client_for(student if signed_in else None).get(f"{reviews_url(place_id)}/viewer")

        assert response.status_code == expected
        assert {"private", "no-store"} <= set(response["Cache-Control"].split(", "))

    def test_public_collection_never_contains_private_viewer_state(
        self, student: Account, library: StudySpot
    ) -> None:
        Review.objects.create(spot=library, author=student, rating=4)
        anonymous = APIClient().get(reviews_url(library.pk))
        signed_in = client_for(student).get(reviews_url(library.pk))

        assert anonymous.status_code == signed_in.status_code == 200
        assert anonymous.json() == signed_in.json()
        assert set(anonymous.json()) == {"items", "summary", "pagination"}
        assert "own_review" not in anonymous.content.decode()
        assert "is_mine" not in anonymous.content.decode()

    @pytest.mark.parametrize("caller_role", ["owner", "student", "anonymous"])
    def test_account_listing_collection_is_private(
        self, owner: Account, student: Account, listing: StudySpot, caller_role: str
    ) -> None:
        caller = {"owner": owner, "student": student, "anonymous": None}[caller_role]
        response = client_for(caller).get("/listings")

        assert response.status_code == {"owner": 200, "student": 403, "anonymous": 401}[caller_role]
        assert {"private", "no-store"} <= set(response["Cache-Control"].split(", "))
        if caller_role == "owner":
            assert [item["id"] for item in response.json()["items"]] == [listing.pk]


class TestEditingOwnReview:
    def test_partial_edit_keeps_unmentioned_scores_and_owner_reply(
        self, student: Account, owner: Account, listing: StudySpot
    ) -> None:
        client = client_for(student)
        original = client.post(reviews_url(listing.pk), REVIEW, format="json").json()
        reply = (
            client_for(owner)
            .put(
                f"{reviews_url(listing.pk)}/{original['id']}/reply",
                {"body": "There are more outlets downstairs."},
                format="json",
            )
            .json()
        )

        response = client.patch(f"{reviews_url(listing.pk)}/mine", {"rating": 5}, format="json")

        assert response.status_code == 200
        edited = response.json()
        assert edited["id"] == original["id"]
        assert edited["rating"] == 5
        assert edited["created_at"] == original["created_at"]
        assert edited["reply"] == reply
        assert {name: edited[name] for name in REVIEW if name != "rating"} == {
            name: value for name, value in REVIEW.items() if name != "rating"
        }
        assert client.get(f"{reviews_url(listing.pk)}/viewer").json()["own_review"] == edited
        assert APIClient().get(reviews_url(listing.pk)).json()["items"] == [edited]

    def test_optional_scores_and_text_can_be_cleared(
        self, student: Account, library: StudySpot
    ) -> None:
        Review.objects.create(spot=library, author=student, **REVIEW)

        response = client_for(student).patch(
            f"{reviews_url(library.pk)}/mine",
            {"noise": None, "wifi": None, "seating": None, "outlets": None, "body": ""},
            format="json",
        )

        assert response.status_code == 200
        assert response.json()["rating"] == REVIEW["rating"]
        assert [response.json()[name] for name in ("noise", "wifi", "seating", "outlets")] == [
            None
        ] * 4
        assert response.json()["body"] == ""

    @pytest.mark.parametrize(
        "change",
        [
            {"rating": None},
            {"rating": 0},
            {"rating": 6},
            {"rating": 2.5},
            {"wifi": 6},
            {"body": "x" * (MAX_REVIEW_BODY + 1)},
            {"author": 1},
            {"id": 1},
            {"spot": "listing:another"},
            {"reply": {"body": "A forged owner reply"}},
            {"created_at": "2020-01-01T00:00:00Z"},
        ],
    )
    def test_invalid_edits_keep_existing_review_and_reply(
        self, student: Account, library: StudySpot, change: dict[str, Any]
    ) -> None:
        review = Review.objects.create(spot=library, author=student, **REVIEW)
        ReviewReply.objects.create(review=review, body="Owner reply")
        before = APIClient().get(reviews_url(library.pk)).json()

        response = client_for(student).patch(
            f"{reviews_url(library.pk)}/mine", change, format="json"
        )

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"
        assert APIClient().get(reviews_url(library.pk)).json() == before

    @pytest.mark.parametrize("method", ["patch", "delete"])
    def test_cannot_mutate_another_students_review(
        self, student: Account, library: StudySpot, method: str
    ) -> None:
        other = account("auth0|other-student")
        review = Review.objects.create(spot=library, author=other, **REVIEW)

        response = getattr(client_for(student), method)(
            f"{reviews_url(library.pk)}/mine", {"rating": 1}, format="json"
        )

        assert response.status_code == (404 if method == "patch" else 204)
        item = APIClient().get(reviews_url(library.pk)).json()["items"][0]
        assert item["id"] == review.pk
        assert item["rating"] == 4

    @pytest.mark.parametrize("method", ["patch", "delete"])
    @pytest.mark.parametrize("role,expected", [(None, 401), (AccountType.BUSINESS, 403), ("", 403)])
    def test_only_signed_in_students_can_mutate(
        self, library: StudySpot, method: str, role: str | None, expected: int
    ) -> None:
        caller = account("auth0|wrong-role", role) if role is not None else None
        response = getattr(client_for(caller), method)(
            f"{reviews_url(library.pk)}/mine", {"rating": 5}, format="json"
        )

        assert response.status_code == expected
        assert response.json()["error"]["code"] == (
            "unauthorized" if expected == 401 else "forbidden"
        )

    @pytest.mark.parametrize("method", ["patch", "delete"])
    def test_unknown_spot_is_not_found(self, student: Account, method: str) -> None:
        response = getattr(client_for(student), method)(
            f"{reviews_url('facdb:missing')}/mine", {"rating": 5}, format="json"
        )

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_deletion_cascades_reply_is_repeatable_and_allows_new_review(
        self, student: Account, library: StudySpot
    ) -> None:
        review = Review.objects.create(spot=library, author=student, **REVIEW)
        ReviewReply.objects.create(review=review, body="Owner reply")
        client = client_for(student)

        for _ in range(2):
            response = client.delete(f"{reviews_url(library.pk)}/mine")
            assert response.status_code == 204
            assert response.content == b""
        assert not ReviewReply.objects.exists()
        assert client.get(f"{reviews_url(library.pk)}/viewer").json() == {
            "kind": "student",
            "own_review": None,
        }
        assert APIClient().get(reviews_url(library.pk)).json()["pagination"]["total"] == 0
        recreated = client.post(reviews_url(library.pk), {"rating": 2}, format="json")
        assert recreated.status_code == 201
        assert recreated.json()["reply"] is None


class TestReplying:
    def test_owner_reply_lifecycle_is_public(
        self, student: Account, owner: Account, listing: StudySpot
    ) -> None:
        review = Review.objects.create(spot=listing, author=student, **REVIEW)
        path = f"{reviews_url(listing.pk)}/{review.pk}/reply"
        client = client_for(owner)

        created = client.put(path, {"body": "Thanks for the feedback."}, format="json")

        assert created.status_code == 201
        assert set(created.json()) == {"body", "created_at", "updated_at"}
        assert created.json()["body"] == "Thanks for the feedback."
        assert created.json()["created_at"]
        assert created.json()["updated_at"]
        assert APIClient().get(reviews_url(listing.pk)).json()["items"][0]["reply"] == (
            created.json()
        )
        updated = client.put(path, {"body": "New outlets are installed."}, format="json")
        assert updated.status_code == 200
        assert updated.json()["body"] == "New outlets are installed."
        assert updated.json()["created_at"] == created.json()["created_at"]
        assert updated.json()["updated_at"] >= created.json()["updated_at"]
        assert ReviewReply.objects.count() == 1
        assert APIClient().get(reviews_url(listing.pk)).json()["items"][0]["reply"] == (
            updated.json()
        )
        retried = client.put(path, {"body": "New outlets are installed."}, format="json")
        assert retried.status_code == 200
        assert retried.json() == updated.json()
        for _ in range(2):
            deleted = client.delete(path)
            assert deleted.status_code == 204
            assert deleted.content == b""
        assert APIClient().get(reviews_url(listing.pk)).json()["items"][0]["reply"] is None
        assert client.put(path, {"body": "A fresh reply."}, format="json").status_code == 201

    @pytest.mark.parametrize("method", ["put", "delete"])
    @pytest.mark.parametrize("role,expected", [(None, 401), (AccountType.STUDENT, 403), ("", 403)])
    def test_reply_requires_a_signed_in_business(
        self, student: Account, listing: StudySpot, method: str, role: str | None, expected: int
    ) -> None:
        review = Review.objects.create(spot=listing, author=student, rating=3)
        caller = account("auth0|reply-wrong-role", role) if role is not None else None

        response = getattr(client_for(caller), method)(
            f"{reviews_url(listing.pk)}/{review.pk}/reply",
            {"body": "Forged reply"},
            format="json",
        )

        assert response.status_code == expected
        assert response.json()["error"]["code"] == (
            "unauthorized" if expected == 401 else "forbidden"
        )
        assert not ReviewReply.objects.exists()

    @pytest.mark.parametrize("method", ["put", "delete"])
    def test_another_owner_cannot_mutate_reply(
        self, student: Account, listing: StudySpot, method: str
    ) -> None:
        review = Review.objects.create(spot=listing, author=student, rating=3)
        reply = ReviewReply.objects.create(review=review, body="Original reply")
        other = account("auth0|another-owner", AccountType.BUSINESS)

        response = getattr(client_for(other), method)(
            f"{reviews_url(listing.pk)}/{review.pk}/reply",
            {"body": "Forged reply"},
            format="json",
        )

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"
        reply.refresh_from_db()
        assert reply.body == "Original reply"

    @pytest.mark.parametrize("method", ["put", "delete"])
    @pytest.mark.parametrize(
        "target", ["imported", "missing", "other-spot-review", "missing-review"]
    )
    def test_review_and_listing_must_both_match(
        self,
        student: Account,
        owner: Account,
        listing: StudySpot,
        library: StudySpot,
        method: str,
        target: str,
    ) -> None:
        foreign_review = Review.objects.create(spot=library, author=student, rating=3)
        place_id = {
            "imported": library.pk,
            "missing": "listing:missing",
            "other-spot-review": listing.pk,
            "missing-review": listing.pk,
        }[target]
        review_id = foreign_review.pk if target != "missing-review" else foreign_review.pk + 99

        response = getattr(client_for(owner), method)(
            f"{reviews_url(place_id)}/{review_id}/reply",
            {"body": "Wrong target"},
            format="json",
        )

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"
        assert not ReviewReply.objects.exists()

    @pytest.mark.parametrize(
        "payload",
        [
            {},
            {"body": ""},
            {"body": "   "},
            {"body": None},
            {"body": "x" * (MAX_REVIEW_BODY + 1)},
            {"body": "Valid", "author": 1},
            {"body": "Valid", "review": 1},
            {"body": "Valid", "updated_at": "2020-01-01T00:00:00Z"},
        ],
    )
    def test_invalid_reply_preserves_existing_content(
        self, student: Account, owner: Account, listing: StudySpot, payload: dict[str, Any]
    ) -> None:
        review = Review.objects.create(spot=listing, author=student, rating=3)
        reply = ReviewReply.objects.create(review=review, body="Original reply")

        response = client_for(owner).put(
            f"{reviews_url(listing.pk)}/{review.pk}/reply", payload, format="json"
        )

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"
        reply.refresh_from_db()
        assert reply.body == "Original reply"

    def test_authorization_follows_current_listing_owner(
        self, student: Account, owner: Account, listing: StudySpot
    ) -> None:
        review = Review.objects.create(spot=listing, author=student, rating=3)
        ReviewReply.objects.create(review=review, body="Original reply")
        successor = account("auth0|successor", AccountType.BUSINESS)
        StudySpot.objects.filter(pk=listing.pk).update(owner=successor)
        path = f"{reviews_url(listing.pk)}/{review.pk}/reply"

        assert client_for(owner).put(path, {"body": "Old owner"}, format="json").status_code == 404
        assert client_for(owner).delete(path).status_code == 404
        assert client_for(owner).get(f"{reviews_url(listing.pk)}/viewer").json() == {
            "kind": "reader"
        }
        assert client_for(successor).get(f"{reviews_url(listing.pk)}/viewer").json() == {
            "kind": "owner"
        }
        response = client_for(successor).put(
            path, {"body": "The new owner responds."}, format="json"
        )
        assert response.status_code == 200
        assert response.json()["body"] == "The new owner responds."

    def test_listing_deletion_cascades_reviews_and_replies(
        self, student: Account, owner: Account, listing: StudySpot
    ) -> None:
        review = Review.objects.create(spot=listing, author=student, rating=3)
        ReviewReply.objects.create(review=review, body="Owner reply")

        assert client_for(owner).delete(f"/listings/{listing.pk}").status_code == 204
        assert not Review.objects.exists()
        assert not ReviewReply.objects.exists()


class TestOverallSummary:
    def test_average_and_count_cover_all_pages_and_only_this_spot(
        self, student: Account, library: StudySpot
    ) -> None:
        Review.objects.create(spot=library, author=student, rating=1)
        Review.objects.create(spot=library, author=account("auth0|summary-b"), rating=2)
        Review.objects.create(spot=library, author=account("auth0|summary-c"), rating=5)
        Review.objects.create(spot=spot("facdb:another"), author=student, rating=5)

        for offset in (0, 1, 2, 10):
            response = APIClient().get(reviews_url(library.pk), {"limit": 1, "offset": offset})
            assert response.status_code == 200
            assert response.json()["pagination"]["total"] == 3
            assert response.json()["summary"]["average_rating"] == pytest.approx(8 / 3)

    def test_summary_tracks_edits_and_deletion(self, student: Account, library: StudySpot) -> None:
        client = client_for(student)
        client.post(reviews_url(library.pk), {"rating": 1}, format="json")
        Review.objects.create(spot=library, author=account("auth0|summary-other"), rating=5)
        assert APIClient().get(reviews_url(library.pk)).json()["summary"] == {"average_rating": 3.0}

        response = client.patch(f"{reviews_url(library.pk)}/mine", {"rating": 3}, format="json")
        assert response.status_code == 200
        assert APIClient().get(reviews_url(library.pk)).json()["summary"] == {"average_rating": 4.0}
        assert client.delete(f"{reviews_url(library.pk)}/mine").status_code == 204
        body = APIClient().get(reviews_url(library.pk)).json()
        assert body["summary"] == {"average_rating": 5.0}
        assert body["pagination"]["total"] == 1
