"""The community API's permission and membership seams against Postgres."""

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from accounts.authentication import Identity
from communities import services
from communities.models import Ban, Channel, Community, Membership

pytestmark = pytest.mark.django_db


def client_for(user=None):
    client = APIClient()
    if user is not None:
        client.force_authenticate(user=user)
    return client


def test_guest_creation_requires_csrf_and_keeps_ownership_in_session():
    guest = APIClient(enforce_csrf_checks=True)
    assert guest.post("/communities", {"name": "Physics"}, format="json").status_code == 403
    guest.get("/communities")
    token = guest.cookies["csrftoken"].value
    created = guest.post("/communities", {"name": "Physics"}, format="json", HTTP_X_CSRFTOKEN=token)
    assert created.status_code == 201
    community_id = created.data["id"]
    assert guest.get(f"/communities/{community_id}").data["role"] == "owner"
    assert (
        guest.patch(
            f"/communities/{community_id}", {"name": "Physics 1"}, HTTP_X_CSRFTOKEN=token
        ).status_code
        == 200
    )
    channel = guest.post(
        f"/communities/{community_id}/channels", {"name": "exams"}, HTTP_X_CSRFTOKEN=token
    )
    assert channel.status_code == 201
    invite = guest.post(f"/communities/{community_id}/invites", {}, HTTP_X_CSRFTOKEN=token)
    assert invite.status_code == 201
    visitor = APIClient(enforce_csrf_checks=True)
    visitor.get("/communities")
    visitor_token = visitor.cookies["csrftoken"].value
    assert visitor.get(f"/communities/{community_id}").data["role"] == "visitor"
    assert (
        visitor.post(
            f"/communities/{community_id}/join", HTTP_X_CSRFTOKEN=visitor_token
        ).status_code
        == 200
    )
    assert visitor.get(f"/communities/{community_id}").data["role"] == "member"
    assert visitor.get(f"/communities/{community_id}").data["member_count"] == 2
    assert visitor.get("/communities?mine=true").data["items"][0]["id"] == community_id
    assert (
        visitor.delete(
            f"/communities/{community_id}/channels/{channel.data['id']}",
            HTTP_X_CSRFTOKEN=visitor_token,
        ).status_code
        == 401
    )
    assert (
        visitor.post(
            f"/communities/{community_id}/leave", HTTP_X_CSRFTOKEN=visitor_token
        ).status_code
        == 200
    )
    assert visitor.get(f"/communities/{community_id}").data["member_count"] == 1
    assert (
        visitor.post(
            f"/communities/invites/{invite.data['token']}/redeem", HTTP_X_CSRFTOKEN=visitor_token
        ).status_code
        == 200
    )
    student = get_user_model().objects.create_user(username="student", password="test-password")
    assert client_for(student).post(f"/communities/{community_id}/join").status_code == 200
    assert visitor.get(f"/communities/{community_id}").data["member_count"] == 3
    assert (
        guest.delete(
            f"/communities/{community_id}/channels/{channel.data['id']}", HTTP_X_CSRFTOKEN=token
        ).status_code
        == 204
    )
    assert not Channel.objects.filter(pk=channel.data["id"]).exists()


def test_auth0_account_can_create_and_manage_community(settings, monkeypatch):
    settings.AUTH0_DOMAIN = "test.auth0.com"
    settings.AUTH0_CLIENT_ID = "client"
    settings.AUTH0_AUDIENCE = "studyspot"
    monkeypatch.setattr(
        "accounts.authentication.verify",
        lambda token, _id_token=None: Identity(token, "", False, ""),
    )
    owner = APIClient()
    owner.credentials(HTTP_AUTHORIZATION="Bearer auth0-owner")
    created = owner.post("/communities", {"name": "Calculus"}, format="json")
    assert created.status_code == 201
    community_id = created.data["id"]
    assert created.data["role"] == "owner"
    assert owner.patch(f"/communities/{community_id}", {"name": "Calculus II"}).status_code == 200
    assert owner.get("/communities?mine=true").data["items"][0]["name"] == "Calculus II"
    stranger = APIClient()
    stranger.credentials(HTTP_AUTHORIZATION="Bearer auth0-stranger")
    assert stranger.patch(f"/communities/{community_id}", {"name": "Nope"}).status_code == 403


def test_create_browse_join_and_owner_rules():
    users = get_user_model().objects
    owner = users.create_user(username="owner", password="test-password")
    member = users.create_user(username="member", password="test-password")
    anonymous = client_for()
    guest_created = anonymous.post("/communities", {"name": "Guest group"}, format="json")
    assert guest_created.status_code == 201
    guest_id = guest_created.data["id"]
    assert guest_created.data["role"] == "owner"
    assert anonymous.patch(f"/communities/{guest_id}", {"name": "Renamed"}).status_code == 200
    assert client_for().patch(f"/communities/{guest_id}", {"name": "Nope"}).status_code == 401
    assert anonymous.get("/communities?mine=true").data["items"][0]["name"] == "Renamed"

    created = client_for(owner).post(
        "/communities", {"name": "Math 51A", "course": "MATH 51A"}, format="json"
    )
    assert created.status_code == 201
    community_id = created.data["id"]
    assert Channel.objects.get(community_id=community_id).name == "general"
    assert anonymous.get("/communities?q=Math").data["items"][0]["name"] == "Math 51A"

    member_client = client_for(member)
    assert member_client.post(f"/communities/{community_id}/join").status_code == 200
    assert member_client.post(f"/communities/{community_id}/join").status_code == 200
    assert Membership.objects.filter(community_id=community_id, user=member).count() == 1
    assert (
        member_client.patch(f"/communities/{community_id}", {"name": "Changed"}).status_code == 403
    )
    assert client_for(owner).post(f"/communities/{community_id}/leave").status_code == 403
    assert (
        client_for(owner)
        .post(f"/communities/{community_id}/transfer", {"user_id": member.id})
        .status_code
        == 200
    )
    assert (
        member_client.patch(f"/communities/{community_id}", {"name": "Changed"}).status_code == 200
    )
    assert client_for(owner).post(f"/communities/{community_id}/leave").status_code == 200


def test_invites_bans_and_moderator_boundaries():
    users = get_user_model().objects
    owner = users.create_user(username="owner", password="test-password")
    moderator = users.create_user(username="mod", password="test-password")
    guest = users.create_user(username="guest", password="test-password")
    community = Community.objects.create(owner=owner, name="Study group")
    Membership.objects.create(community=community, user=owner)
    Membership.objects.create(community=community, user=moderator, role="moderator")
    base = f"/communities/{community.pk}"

    response = client_for(moderator).post(f"{base}/invites", {"max_uses": 1}, format="json")
    assert response.status_code == 201
    assert (
        client_for(guest).post(f"/communities/invites/{response.data['token']}/redeem").status_code
        == 200
    )
    assert (
        client_for(guest).post(f"/communities/invites/{response.data['token']}/redeem").status_code
        == 404
    )
    assert (
        client_for(moderator)
        .post(f"{base}/moderation", {"user_id": guest.id, "action": "ban"})
        .status_code
        == 200
    )
    assert Ban.objects.filter(community=community, user=guest).exists()
    assert client_for(guest).post(f"{base}/join").status_code == 403
    assert (
        client_for(moderator)
        .post(f"{base}/moderation", {"user_id": owner.id, "action": "ban"})
        .status_code
        == 403
    )
    assert (
        client_for(moderator).patch(f"{base}/members/{owner.id}", {"role": "member"}).status_code
        == 403
    )
    assert (
        client_for(owner)
        .post(f"{base}/moderation", {"user_id": guest.id, "action": "unban"})
        .status_code
        == 200
    )
    assert client_for(guest).post(f"{base}/join").status_code == 200


def test_channels_are_scoped_and_name_unique():
    user = get_user_model().objects.create_user(username="owner", password="test-password")
    first = Community.objects.create(owner=user, name="First")
    second = Community.objects.create(owner=user, name="Second")
    client = client_for(user)
    created = client.post(f"/communities/{first.pk}/channels", {"name": "homework"})
    assert created.status_code == 201
    channel_id = created.data["id"]
    assert client.post(f"/communities/{first.pk}/channels", {"name": "homework"}).status_code == 422
    assert (
        client.patch(
            f"/communities/{second.pk}/channels/{channel_id}", {"archived": True}
        ).status_code
        == 404
    )
    assert (
        client.patch(
            f"/communities/{first.pk}/channels/{channel_id}", {"archived": True}
        ).status_code
        == 200
    )
    other = client.post(f"/communities/{first.pk}/channels", {"name": "exams"}).data["id"]
    assert (
        client.patch(f"/communities/{first.pk}/channels/{other}", {"position": 0}).status_code
        == 200
    )
    assert list(first.channels.values_list("name", flat=True)) == ["exams", "homework"]


def test_session_requires_csrf_and_staff_action_is_separate():
    users = get_user_model().objects
    users.create_user(username="owner", password="test-password")
    staff = users.create_user(username="staff", password="test-password", is_staff=True)
    client = APIClient(enforce_csrf_checks=True)
    client.get("/admin/login/")
    assert client.login(username="owner", password="test-password")
    assert client.post("/communities", {"name": "Course"}, format="json").status_code == 403
    token = client.cookies["csrftoken"].value
    response = client.post(
        "/communities",
        {"name": "Course"},
        format="json",
        HTTP_X_CSRFTOKEN=token,
        HTTP_ORIGIN="http://localhost:7500",
    )
    assert response.status_code == 201
    community_id = response.data["id"]
    assert (
        client.delete(f"/communities/{community_id}/admin", HTTP_X_CSRFTOKEN=token).status_code
        == 403
    )
    assert client_for(staff).delete(f"/communities/{community_id}/admin").status_code == 204


def test_member_cap_is_enforced(monkeypatch):
    monkeypatch.setattr(services, "MAX_MEMBERS", 2)
    users = get_user_model().objects
    owner = users.create_user(username="owner", password="test-password")
    community = Community.objects.create(owner=owner, name="Full group")
    Membership.objects.create(community=community, user=owner)
    first = users.create_user(username="first", password="test-password")
    second = users.create_user(username="second", password="test-password")
    assert client_for(first).post(f"/communities/{community.pk}/join").status_code == 200
    assert client_for(second).post(f"/communities/{community.pk}/join").status_code == 422
