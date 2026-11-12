"""Local message samples belong to the requesting browser session."""

import pytest
from rest_framework.test import APIClient

from communities.models import Community, DirectConversation, DirectMessage, Poll


def demo_client() -> APIClient:
    client = APIClient(enforce_csrf_checks=True)
    client.get("/communities/access")
    client.credentials(HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value)
    return client


@pytest.mark.django_db
def test_demo_setup_is_repeatable_and_samples_are_usable(settings):
    settings.DEBUG = True
    settings.CHAT_GUEST_ACCESS = True
    settings.CHAT_GUEST_DEMO = True
    client = demo_client()
    assert client.post("/chat/demo").status_code == 200
    counts = [
        model.objects.count() for model in (Community, DirectConversation, DirectMessage, Poll)
    ]
    assert client.post("/chat/demo").status_code == 200
    assert [
        model.objects.count() for model in (Community, DirectConversation, DirectMessage, Poll)
    ] == counts
    conversations = client.get("/dms").data["items"]
    assert {item["other_name"] for item in conversations} == {
        "Maya Chen",
        "Jordan Rivera",
        "Thursday study crew",
    }
    group = next(item for item in conversations if item["kind"] == "group")
    assert group["member_count"] == 3
    assert client.get(f"/dms/{group['id']}/messages").data["items"]
    room = next(item["id"] for item in conversations if item["other_name"] == "Maya Chen")
    messages = client.get(f"/dms/{room}/messages").data["items"]
    assert any(item["mine"] for item in messages)
    assert any(item["poll"] for item in messages)
    assert any(item["pinned_at"] for item in messages)
    assert any(item["reactions"] for item in messages)
    attachment = next(item for item in messages if item["file_name"])
    assert client.get(f"/dms/{room}/messages/{attachment['id']}?attachment=1").status_code == 200
    assert (
        client.post(
            f"/dms/{room}/messages", {"content": "Trying the demo"}, format="json"
        ).status_code
        == 201
    )


@pytest.mark.django_db
def test_demo_sessions_have_separate_private_conversations(settings):
    settings.DEBUG = True
    settings.CHAT_GUEST_ACCESS = True
    settings.CHAT_GUEST_DEMO = True
    first, second = demo_client(), demo_client()
    assert first.post("/chat/demo").status_code == 200
    assert second.post("/chat/demo").status_code == 200
    first_room = first.get("/dms").data["items"][0]["id"]
    assert second.get(f"/dms/{first_room}/messages").status_code == 404


@pytest.mark.django_db
@pytest.mark.parametrize(("debug", "demo"), [(False, True), (True, False)])
def test_demo_setup_is_unavailable_outside_local_demo(settings, debug, demo):
    settings.DEBUG = debug
    settings.CHAT_GUEST_DEMO = demo
    assert demo_client().post("/chat/demo").status_code == 404


@pytest.mark.django_db
def test_demo_setup_requires_csrf(settings):
    settings.DEBUG = True
    settings.CHAT_GUEST_DEMO = True
    assert APIClient(enforce_csrf_checks=True).post("/chat/demo").status_code == 403
