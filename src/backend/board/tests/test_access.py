import pytest
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.db import IntegrityError, transaction
from rest_framework.test import APIClient

from accounts.authentication import Identity
from accounts.models import Account
from board.models import Comment, Post

pytestmark = pytest.mark.django_db


def test_guest_access_issues_csrf_and_private_writer_capabilities(guest_client):
    client = guest_client()
    response = client.get("/board/access")
    assert response.data["viewer"] == "guest"
    assert response.data["create_kinds"] == ["question", "information"]
    assert response.data["can_comment"] and response.data["can_report"]
    assert "csrftoken" in response.cookies
    assert response["Cache-Control"] == "private, no-store"
    assert "Authorization" in response["Vary"]
    assert "community_guest_id" in client.session
    assert client.session["community_guest_id"] not in str(response.data)


def test_cookieless_public_reads_do_not_create_sessions_or_hide_report_capability(
    guest_client, draft
):
    owner = guest_client()
    post = owner.post("/board/posts", draft, format="json").data
    owner.post(f"/board/posts/{post['id']}/comments", {"body": "A public reply"})
    before = Session.objects.count()
    for path in [
        "/board/posts",
        f"/board/posts/{post['id']}",
        f"/board/posts/{post['id']}/comments",
        "/board/tags",
    ]:
        client = APIClient(enforce_csrf_checks=True)
        response = client.get(path)
        assert response.status_code == 200
        assert "sessionid" not in response.cookies
        assert Session.objects.count() == before
    public = APIClient().get(f"/board/posts/{post['id']}").data
    assert public["can_report"] is True
    assert public["can_edit"] is False
    assert public["can_delete"] is False


def test_first_write_establishes_guest_identity_without_access_bootstrap(draft):
    client = APIClient(enforce_csrf_checks=True)
    client.get("/board/posts")
    assert "sessionid" not in client.cookies
    client.credentials(HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value)
    created = client.post("/board/posts", draft, format="json")
    assert created.status_code == 201
    assert "sessionid" in created.cookies
    assert client.get(f"/board/posts/{created.data['id']}").data["can_edit"] is True


def test_public_reads_remain_available_when_guests_are_disabled(settings, guest_client, draft):
    owner = guest_client()
    created = owner.post("/board/posts", draft, format="json")
    post_id = created.data["id"]
    settings.CHAT_GUEST_ACCESS = False
    visitor = APIClient(enforce_csrf_checks=True)
    access = visitor.get("/board/access")
    assert access.data["viewer"] == "visitor"
    assert access.data["create_kinds"] == []
    assert not access.data["can_comment"]
    assert visitor.get("/board/posts").data["items"][0]["id"] == post_id
    assert visitor.get(f"/board/posts/{post_id}").status_code == 200
    assert visitor.get(f"/board/posts/{post_id}/comments").status_code == 200
    assert visitor.get("/board/tags").status_code == 200
    visitor.credentials(HTTP_X_CSRFTOKEN=visitor.cookies["csrftoken"].value)
    assert visitor.post("/board/posts", draft, format="json").status_code == 401
    assert owner.patch(f"/board/posts/{post_id}", {"title": "No"}, format="json").status_code == 401
    assert visitor.post(f"/board/posts/{post_id}/comments", {"body": "No"}).status_code == 401
    assert visitor.post(f"/board/posts/{post_id}/reports", {"reason": "No"}).status_code == 401


def test_guest_writes_require_csrf_including_update_delete_comment_and_report(guest_client, draft):
    owner = guest_client()
    post = owner.post("/board/posts", draft, format="json").data
    comment = owner.post(
        f"/board/posts/{post['id']}/comments", {"body": "A reply"}, format="json"
    ).data
    owner.credentials()
    requests = [
        owner.post("/board/posts", draft, format="json"),
        owner.patch(f"/board/posts/{post['id']}", {"title": "No"}, format="json"),
        owner.delete(f"/board/posts/{post['id']}"),
        owner.post(f"/board/posts/{post['id']}/comments", {"body": "No"}, format="json"),
        owner.patch(f"/board/comments/{comment['id']}", {"body": "No"}, format="json"),
        owner.delete(f"/board/comments/{comment['id']}"),
        owner.post(f"/board/posts/{post['id']}/reports", {"reason": "No"}, format="json"),
        owner.post(f"/board/comments/{comment['id']}/reports", {"reason": "No"}, format="json"),
    ]
    assert all(response.status_code == 403 for response in requests)
    assert all(response["Cache-Control"] == "private, no-store" for response in requests)
    assert Post.objects.get(pk=post["id"]).title == draft["title"]
    assert Comment.objects.get(pk=comment["id"]).body == "A reply"


def test_session_account_writes_also_require_csrf(account_client, draft):
    _, account = account_client()
    client = APIClient(enforce_csrf_checks=True)
    client.force_login(account.user)
    client.get("/board/access")
    assert client.post("/board/posts", draft, format="json").status_code == 403
    client.credentials(HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value)
    response = client.post("/board/posts", draft, format="json")
    assert response.status_code == 201
    assert response.data["author"] == {"kind": "student", "name": account.username}


@pytest.mark.parametrize(
    "kind,active,viewer", [("", True, "unfinished"), ("student", False, "inactive")]
)
def test_ineligible_account_never_falls_back_to_existing_guest(
    account_client, guest_client, draft, kind, active, viewer
):
    guest = guest_client()
    owner_post = guest.post("/board/posts", draft, format="json").data
    _, account = account_client(kind, active=active)
    guest.force_authenticate(user=account.user)
    access = guest.get("/board/access")
    assert access.data["viewer"] == viewer
    assert access.data["guest_access"] is True
    assert access.data["create_kinds"] == []
    assert guest.get("/board/posts").status_code == 200
    assert guest.post("/board/posts", draft, format="json").status_code == 403
    assert (
        guest.post(f"/board/posts/{owner_post['id']}/comments", {"body": "No"}).status_code == 403
    )
    assert (
        guest.post(f"/board/posts/{owner_post['id']}/reports", {"reason": "No"}).status_code == 403
    )
    assert guest.delete(f"/board/posts/{owner_post['id']}").status_code == 403


def test_user_without_completed_account_is_not_a_guest(guest_client, draft):
    guest = guest_client()
    user = get_user_model().objects.create_user(username="auth0|no-account")
    guest.force_authenticate(user=user)
    assert guest.get("/board/access").data["viewer"] == "unfinished"
    assert guest.post("/board/posts", draft, format="json").status_code == 403


@pytest.mark.parametrize("kind", ["student", "business"])
def test_completed_accounts_use_account_display_names_and_kind_rules(account_client, draft, kind):
    client, account = account_client(kind)
    access = client.get("/board/access")
    assert access.data["viewer"] == kind
    assert ("announcement" in access.data["create_kinds"]) is (kind == "business")
    response = client.post("/board/posts", draft, format="json")
    assert response.status_code == 201
    expected = account.business_name if kind == "business" else account.username
    assert response.data["author"] == {"kind": kind, "name": expected}
    assert account.user.username not in str(response.data)
    assert account.email not in str(response.data)
    announcement = client.post("/board/posts", {**draft, "kind": "announcement"}, format="json")
    assert announcement.status_code == (201 if kind == "business" else 422)


def test_guests_cannot_publish_announcements(guest_client, draft):
    response = guest_client().post("/board/posts", {**draft, "kind": "announcement"}, format="json")
    assert response.status_code == 422
    assert not Post.objects.exists()


def test_auth0_identity_is_not_replaced_with_a_guest(settings, monkeypatch, draft):
    settings.ACCOUNTS_ENABLED = True
    settings.AUTH0_DOMAIN = "test.auth0.com"
    settings.AUTH0_CLIENT_ID = "client"
    settings.AUTH0_AUDIENCE = "studyspot"
    user = get_user_model().objects.create_user(username="auth0|board-bearer")
    Account.objects.create(user=user, account_type="student", username="BearerStudent")
    monkeypatch.setattr(
        "accounts.authentication.verify",
        lambda token, _id_token=None: Identity("auth0|board-bearer", "", False, ""),
    )
    client = APIClient(enforce_csrf_checks=True)
    client.credentials(HTTP_AUTHORIZATION="Bearer local-test-token")
    response = client.post("/board/posts", draft, format="json")
    assert response.status_code == 201
    assert response.data["author"] == {"kind": "student", "name": "BearerStudent"}
    user.is_active = False
    user.save(update_fields=["is_active"])
    assert client.get("/board/access").data["viewer"] == "inactive"
    assert client.post("/board/posts", draft, format="json").status_code == 403


def test_deleted_account_snapshots_cannot_be_claimed_by_a_guest(
    account_client, guest_client, draft
):
    client, account = account_client()
    response = client.post("/board/posts", draft, format="json")
    post_id = response.data["id"]
    name = account.username
    account.user.delete()
    post = Post.objects.get(pk=post_id)
    assert post.author_account_id is None
    assert post.author_guest_id == ""
    guest = guest_client()
    detail = guest.get(f"/board/posts/{post_id}")
    assert detail.data["author"] == {"kind": "student", "name": name}
    assert not detail.data["can_edit"]
    assert guest.delete(f"/board/posts/{post_id}").status_code == 403


@pytest.mark.parametrize(
    "stamp",
    [
        {"author_kind": "guest", "author_guest_id": ""},
        {"author_kind": "student", "author_guest_id": "guest"},
        {"author_kind": "unknown", "author_guest_id": ""},
    ],
)
def test_database_rejects_ambiguous_author_stamps(stamp):
    with pytest.raises(IntegrityError), transaction.atomic():
        Post.objects.create(title="Bad", body="Bad", kind="question", author_name="Name", **stamp)


def test_database_rejects_guest_stamp_with_account(account_client):
    _, account = account_client()
    with pytest.raises(IntegrityError), transaction.atomic():
        Post.objects.create(
            title="Bad",
            body="Bad",
            kind="question",
            author_name="Name",
            author_kind="guest",
            author_guest_id="guest",
            author_account=account,
        )


def test_inactive_django_session_cannot_fall_back_to_guest(account_client, draft):
    _, account = account_client(active=False)
    client = APIClient(enforce_csrf_checks=True)
    client.force_login(account.user)
    response = client.get("/board/access")
    assert response.data["viewer"] == "inactive"
    assert response.data["create_kinds"] == []
    client.credentials(HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value)
    assert client.post("/board/posts", draft, format="json").status_code == 403
