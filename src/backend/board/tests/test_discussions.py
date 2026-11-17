from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Barrier

import pytest
from django.db import close_old_connections, connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from board.models import Comment, Post, PostTag, Report, Tag
from spots.models import StudySpot

pytestmark = pytest.mark.django_db


def test_discussion_lifecycle_is_owned_persistent_and_private(guest_client, draft):
    owner = guest_client()
    other = guest_client()
    response = owner.post("/board/posts", draft, format="json")
    assert response.status_code == 201
    post = response.data
    post_id = post["id"]
    assert set(post) == {
        "id",
        "kind",
        "title",
        "body",
        "tags",
        "author",
        "created_at",
        "updated_at",
        "comment_count",
        "can_edit",
        "can_delete",
        "can_report",
    }
    assert set(post["author"]) == {"kind", "name"}
    assert post["can_edit"] and post["can_delete"] and post["can_report"]
    assert post["comment_count"] == 0
    assert owner.get(f"/board/posts/{post_id}").data == post
    public = other.get(f"/board/posts/{post_id}").data
    assert not public["can_edit"] and not public["can_delete"]
    assert (
        other.patch(f"/board/posts/{post_id}", {"title": "Stolen"}, format="json").status_code
        == 403
    )
    assert other.delete(f"/board/posts/{post_id}").status_code == 403
    assert Post.objects.get(pk=post_id).title == draft["title"]
    reply = other.post(
        f"/board/posts/{post_id}/comments", {"body": "  Try the library.  "}, format="json"
    )
    assert reply.status_code == 201
    comment = reply.data
    assert set(comment) == {
        "id",
        "post_id",
        "body",
        "author",
        "created_at",
        "updated_at",
        "can_edit",
        "can_delete",
        "can_report",
    }
    assert comment["post_id"] == post_id
    assert comment["body"] == "Try the library."
    assert other.get(f"/board/posts/{post_id}/comments").data["items"][0] == comment
    assert owner.get(f"/board/posts/{post_id}").data["comment_count"] == 1
    assert owner.get("/board/posts").data["items"][0]["comment_count"] == 1
    assert owner.patch(f"/board/comments/{comment['id']}", {"body": "No"}).status_code == 403
    assert owner.delete(f"/board/comments/{comment['id']}").status_code == 403
    changed = other.patch(
        f"/board/comments/{comment['id']}", {"body": "Updated reply"}, format="json"
    )
    assert changed.status_code == 200
    assert other.get(f"/board/posts/{post_id}/comments").data["items"][0]["body"] == "Updated reply"
    edited = owner.patch(
        f"/board/posts/{post_id}",
        {
            "title": "Updated title",
            "body": "Updated\nbody",
            "tags": [{"kind": "subject", "value": "Physics"}],
        },
        format="json",
    )
    assert edited.status_code == 200
    assert edited.data["kind"] == "question"
    assert edited.data["author"] == post["author"]
    assert edited.data["created_at"] == post["created_at"]
    assert edited.data["tags"] == [
        {"kind": "subject", "value": "physics", "label": "Physics", "available": True}
    ]
    assert owner.get(f"/board/posts/{post_id}").data["body"] == "Updated\nbody"
    assert other.delete(f"/board/comments/{comment['id']}").status_code == 204
    assert owner.get(f"/board/posts/{post_id}").data["comment_count"] == 0
    other.post(f"/board/posts/{post_id}/comments", {"body": "Second reply"}, format="json")
    assert owner.delete(f"/board/posts/{post_id}").status_code == 204
    assert not Comment.objects.filter(post_id=post_id).exists()
    assert not PostTag.objects.filter(post_id=post_id).exists()
    assert owner.get(f"/board/posts/{post_id}").status_code == 404
    assert owner.get(f"/board/posts/{post_id}/comments").status_code == 404
    assert owner.post(f"/board/posts/{post_id}/comments", {"body": "Orphan"}).status_code == 404


def test_staff_has_no_implicit_api_edit_privilege(account_client, draft):
    owner, _ = account_client()
    staff, _ = account_client(staff=True)
    post = owner.post("/board/posts", draft, format="json").data
    comment = owner.post(f"/board/posts/{post['id']}/comments", {"body": "Reply"}).data
    assert not staff.get(f"/board/posts/{post['id']}").data["can_edit"]
    assert staff.patch(f"/board/posts/{post['id']}", {"body": "No"}).status_code == 403
    assert staff.delete(f"/board/comments/{comment['id']}").status_code == 403


def test_tag_identity_normalizes_unicode_whitespace_and_case(guest_client, draft):
    owner = guest_client()
    response = owner.post(
        "/board/posts",
        {
            **draft,
            "tags": [
                {"kind": "subject", "value": "  Ｌinear\n  Algebra "},
                {"kind": "subject", "value": "linear algebra"},
                {"kind": "university", "value": "  Universität   Straße "},
                {"kind": "subject", "value": "Physics"},
            ],
        },
        format="json",
    )
    assert response.status_code == 201
    tags = response.data["tags"]
    assert len(tags) == 3
    assert {tag["value"] for tag in tags} == {"linear algebra", "universität strasse", "physics"}
    assert all(tag["available"] for tag in tags)
    other = owner.post(
        "/board/posts",
        {**draft, "tags": [{"kind": "subject", "value": "LINEAR ALGEBRA"}]},
        format="json",
    )
    assert other.status_code == 201
    assert Tag.objects.filter(kind="subject", key="linear algebra").count() == 1
    suggestions = owner.get("/board/tags", {"kind": "subject", "q": "ＬINEAR"}).data["items"]
    assert len(suggestions) == 1
    assert suggestions[0]["post_count"] == 2
    assert suggestions[0]["value"] == "linear algebra"
    assert len(owner.get("/board/posts", {"university": "UNIVERSITÄT STRASSE"}).data["items"]) == 1


def test_ten_distinct_tags_allow_duplicates_and_casefold_expansion(guest_client, draft):
    tags = [{"kind": "subject", "value": f"Topic {index}"} for index in range(10)]
    owner = guest_client()
    response = owner.post("/board/posts", {**draft, "tags": [*tags, tags[0]]}, format="json")
    assert response.status_code == 201
    assert len(response.data["tags"]) == 10
    assert (
        owner.post(
            "/board/posts",
            {**draft, "tags": [*tags, {"kind": "subject", "value": "Eleventh"}]},
            format="json",
        ).status_code
        == 422
    )
    expanded = owner.post(
        "/board/posts",
        {**draft, "tags": [{"kind": "university", "value": "ΐ" * 120}]},
        format="json",
    )
    assert expanded.status_code == 201
    assert expanded.data["tags"][0]["value"] == ("ΐ" * 120).casefold()


def test_spot_tags_validate_stable_ids_and_survive_source_refresh(guest_client, draft, spot):
    owner = guest_client()
    response = owner.post(
        "/board/posts", {**draft, "tags": [{"kind": "spot", "value": spot.pk}]}, format="json"
    )
    assert response.status_code == 201
    post_id = response.data["id"]
    original = response.data["tags"][0]
    assert original == {"kind": "spot", "value": spot.pk, "label": spot.name, "available": True}
    assert (
        owner.post(
            "/board/posts",
            {**draft, "tags": [{"kind": "spot", "value": spot.pk.lower()}]},
            format="json",
        ).status_code
        == 422
    )
    assert (
        owner.post(
            "/board/posts",
            {**draft, "tags": [{"kind": "spot", "value": "missing:spot"}]},
            format="json",
        ).status_code
        == 422
    )
    spot_id = spot.pk
    spot.delete()
    assert Post.objects.filter(pk=post_id).exists()
    retained = owner.get(f"/board/posts/{post_id}").data["tags"][0]
    assert retained == {**original, "available": False}
    assert (
        owner.patch(f"/board/posts/{post_id}", {"title": "Still here"}, format="json").status_code
        == 200
    )
    assert (
        owner.patch(
            f"/board/posts/{post_id}", {"tags": [{"kind": "spot", "value": spot_id}]}, format="json"
        ).status_code
        == 200
    )
    assert (
        owner.post(
            "/board/posts", {**draft, "tags": [{"kind": "spot", "value": spot_id}]}, format="json"
        ).status_code
        == 422
    )
    assert owner.get("/board/posts", {"spot": spot_id}).data["items"][0]["id"] == post_id
    assert owner.get("/board/tags", {"kind": "spot"}).data["items"][0]["available"] is False
    StudySpot.objects.create(
        id=spot_id,
        name="Renamed source library",
        category="public_library",
        borough="Manhattan",
        latitude=40.73,
        longitude=-73.99,
    )
    restored = owner.get(f"/board/posts/{post_id}").data["tags"][0]
    assert restored["available"] is True
    assert restored["label"] == "Renamed source library"


def test_keyword_and_each_structured_tag_filter_compose(guest_client, draft, spot):
    owner = guest_client()
    tags = [*draft["tags"], {"kind": "spot", "value": spot.pk}]
    target = owner.post("/board/posts", {**draft, "tags": tags}, format="json").data
    owner.post(
        "/board/posts", {**draft, "title": "Other", "body": "Unrelated", "tags": []}, format="json"
    )
    owner.post(
        "/board/posts",
        {**draft, "title": "Calculus elsewhere", "body": "Unrelated", "tags": []},
        format="json",
    )
    for query in [
        {"q": "INTEGRALS"},
        {"subject": "  CALCULUS  "},
        {"university": "new york university"},
        {"spot": spot.pk},
        {
            "q": "quiet",
            "subject": "calculus",
            "university": "New York University",
            "spot": spot.pk,
            "kind": "question",
        },
    ]:
        assert [post["id"] for post in owner.get("/board/posts", query).data["items"]] == [
            target["id"]
        ]
    assert owner.get("/board/posts", {"q": "absent", "subject": "calculus"}).data["items"] == []
    assert owner.get("/board/posts", {"spot": spot.pk.lower()}).data["items"] == []
    assert owner.get("/board/posts", {"kind": "information"}).data["items"] == []
    assert len(owner.get("/board/posts").data["items"]) == 3


def test_post_and_comment_keyset_pagination(guest_client, draft):
    owner = guest_client()
    ids = [owner.post("/board/posts", draft, format="json").data["id"] for _ in range(5)]
    first = owner.get("/board/posts", {"limit": 2}).data
    assert [post["id"] for post in first["items"]] == ids[::-1][:2]
    assert first["has_more"] is True
    owner.post("/board/posts", draft, format="json")
    second = owner.get("/board/posts", {"limit": 2, "before": first["items"][-1]["id"]}).data
    assert [post["id"] for post in second["items"]] == [ids[2], ids[1]]
    last = owner.get("/board/posts", {"limit": 2, "before": second["items"][-1]["id"]}).data
    assert [post["id"] for post in last["items"]] == [ids[0]]
    assert last["has_more"] is False
    post_id = ids[0]
    comments = [
        owner.post(f"/board/posts/{post_id}/comments", {"body": str(i)}).data["id"]
        for i in range(5)
    ]
    page = owner.get(f"/board/posts/{post_id}/comments", {"limit": 2}).data
    assert [comment["id"] for comment in page["items"]] == comments[:2]
    assert page["has_more"] is True
    page = owner.get(f"/board/posts/{post_id}/comments", {"limit": 3, "after": comments[1]}).data
    assert [comment["id"] for comment in page["items"]] == comments[2:]
    assert page["has_more"] is False


def test_suggestions_only_include_used_tags_and_are_bounded(guest_client, draft):
    owner = guest_client()
    Tag.objects.create(kind="subject", key="unused", label="Unused")
    post = owner.post("/board/posts", draft, format="json").data
    assert owner.get("/board/tags", {"q": "unused"}).data == {"items": []}
    assert len(owner.get("/board/tags", {"limit": 1}).data["items"]) == 1
    first = owner.get("/board/tags").data
    assert owner.get("/board/tags").data == first
    owner.delete(f"/board/posts/{post['id']}")
    assert owner.get("/board/tags").data == {"items": []}


def test_feed_queries_do_not_grow_per_post(guest_client, draft, spot):
    owner = guest_client()
    for index in range(7):
        post = owner.post(
            "/board/posts",
            {**draft, "title": f"Post {index}", "tags": [{"kind": "spot", "value": spot.pk}]},
            format="json",
        ).data
        owner.post(f"/board/posts/{post['id']}/comments", {"body": "Reply"})
    visitor = APIClient()
    visitor.get("/board/access")
    with CaptureQueriesContext(connection) as single:
        one = visitor.get("/board/posts", {"limit": 1})
    with CaptureQueriesContext(connection) as multiple:
        many = visitor.get("/board/posts", {"limit": 7})
    assert one.status_code == many.status_code == 200
    assert len(single) == len(multiple)
    assert all(item["comment_count"] == 1 for item in many.data["items"])
    assert all(item["tags"][0]["available"] for item in many.data["items"])


@pytest.mark.parametrize(
    "change",
    [
        {"title": ""},
        {"title": " "},
        {"title": "x" * 161},
        {"body": ""},
        {"body": "x" * 10001},
        {"body": 123},
        {"kind": "other"},
        {"author": {"kind": "business", "name": "Fake"}},
        {"author_account": 1},
        {"can_edit": True},
        {"tags": [{"kind": "other", "value": "bad"}]},
        {"tags": [{"kind": "subject", "value": " "}]},
        {"tags": [{"kind": "subject", "value": "x" * 81}]},
        {"tags": [{"kind": "university", "value": "x" * 121}]},
        {"tags": [{"kind": "spot", "value": "x" * 256}]},
        {"tags": [{"kind": "spot", "value": "real", "label": "Fake name"}]},
    ],
)
def test_post_input_validation_is_atomic_and_uses_error_envelope(guest_client, draft, change):
    owner = guest_client()
    response = owner.post("/board/posts", {**draft, **change}, format="json")
    assert response.status_code == 422
    assert response.data["error"]["code"] == "validation_error"
    assert response.data["error"]["details"]
    assert response["Cache-Control"] == "private, no-store"
    assert not Post.objects.exists()
    assert not Tag.objects.exists()


@pytest.mark.parametrize(
    "change", [{}, {"tags": [{"kind": "subject"}]}, {"tags": [{"value": "Math"}]}, {"id": 1}]
)
def test_partial_updates_need_nonempty_complete_writable_values(guest_client, draft, change):
    owner = guest_client()
    post = owner.post("/board/posts", draft, format="json").data
    assert owner.patch(f"/board/posts/{post['id']}", change, format="json").status_code == 422
    assert owner.get(f"/board/posts/{post['id']}").data == post


@pytest.mark.parametrize("body", ["", " ", "x" * 3001, None, 123])
def test_comment_input_boundaries(guest_client, draft, body):
    owner = guest_client()
    post = owner.post("/board/posts", draft, format="json").data
    response = owner.post(f"/board/posts/{post['id']}/comments", {"body": body}, format="json")
    assert response.status_code == 422
    assert not Comment.objects.exists()


def test_comment_cannot_be_reassigned_and_field_limits_accept_exact_maximum(guest_client, draft):
    owner = guest_client()
    first = owner.post(
        "/board/posts", {**draft, "title": "x" * 160, "body": "x" * 10000}, format="json"
    )
    assert first.status_code == 201
    second = owner.post("/board/posts", draft, format="json").data
    comment = owner.post(
        f"/board/posts/{first.data['id']}/comments", {"body": "x" * 3000}, format="json"
    )
    assert comment.status_code == 201
    assert (
        owner.patch(
            f"/board/comments/{comment.data['id']}",
            {"body": "Changed", "post_id": second["id"]},
            format="json",
        ).status_code
        == 422
    )
    assert Comment.objects.get(pk=comment.data["id"]).post_id == first.data["id"]


@pytest.mark.parametrize(
    "path",
    [
        "/board/posts?limit=0",
        "/board/posts?limit=51",
        "/board/posts?before=-1",
        "/board/posts?before=not-an-id",
        "/board/posts?before=9223372036854775808",
        "/board/posts?kind=other",
        "/board/tags?kind=other",
        "/board/tags?limit=51",
        "/board/posts?author_account=1",
    ],
)
def test_query_validation_returns_private_422(path):
    response = APIClient().get(path)
    assert response.status_code == 422
    assert response.data["error"]["code"] == "validation_error"
    assert response["Cache-Control"] == "private, no-store"


def test_comment_query_validation_and_missing_resources(guest_client, draft):
    owner = guest_client()
    post = owner.post("/board/posts", draft, format="json").data
    assert owner.get(f"/board/posts/{post['id']}/comments?after=0").status_code == 422
    assert owner.get(f"/board/posts/{post['id']}/comments?limit=51").status_code == 422
    assert owner.get("/board/posts/999999").status_code == 404
    assert owner.patch("/board/comments/999999", {"body": "Missing"}).status_code == 404
    assert owner.delete("/board/comments/999999").status_code == 404


@pytest.mark.django_db(transaction=True)
def test_concurrent_posts_share_new_tags_submitted_in_opposite_orders(guest_client, draft):
    authors = [guest_client(), guest_client()]
    tags = [
        {"kind": "subject" if index % 2 else "university", "value": f"Concurrent {index}"}
        for index in range(10)
    ]
    barrier = Barrier(2)

    def publish(index):
        close_old_connections()
        try:
            client = APIClient(enforce_csrf_checks=True)
            client.cookies = deepcopy(authors[index].cookies)
            client.credentials(HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value)
            barrier.wait(timeout=10)
            response = client.post(
                "/board/posts",
                {**draft, "tags": tags if index == 0 else tags[::-1]},
                format="json",
            )
            return response.status_code, response.json()
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(publish, range(2)))
    assert [status for status, _ in results] == [201, 201]
    assert Post.objects.count() == 2
    assert Tag.objects.count() == 10
    expected = {(tag["kind"], tag["value"].casefold()) for tag in tags}
    for _, post in results:
        assert {(tag["kind"], tag["value"]) for tag in post["tags"]} == expected


@pytest.mark.parametrize("text", ["\u200b", "\u3164", "\u2800", "\u0301\ufe0f\u200d"])
def test_invisible_only_content_is_rejected_at_every_write_boundary(guest_client, draft, text):
    owner = guest_client()
    for change in [
        {"title": text},
        {"body": text},
        {"tags": [{"kind": "subject", "value": text}]},
    ]:
        assert owner.post("/board/posts", {**draft, **change}, format="json").status_code == 422
    post = owner.post("/board/posts", draft, format="json").data
    assert owner.post(f"/board/posts/{post['id']}/comments", {"body": text}).status_code == 422
    assert owner.post(f"/board/posts/{post['id']}/reports", {"reason": text}).status_code == 422
    assert Post.objects.count() == 1
    assert not Comment.objects.exists()
    assert not Report.objects.exists()


def test_visible_multilingual_text_keeps_combining_marks_and_emoji_joiners(guest_client, draft):
    owner = guest_client()
    title = "数学の勉強 👩‍💻"
    body = "مراجعة لِلجبر\nBraille \u2801"
    created = owner.post(
        "/board/posts",
        {
            **draft,
            "title": title,
            "body": body,
            "tags": [{"kind": "subject", "value": "Équations"}],
        },
        format="json",
    )
    assert created.status_code == 201
    stored = owner.get(f"/board/posts/{created.data['id']}").data
    assert stored["title"] == title
    assert stored["body"] == body
    assert stored["tags"][0]["label"] == "Équations"
