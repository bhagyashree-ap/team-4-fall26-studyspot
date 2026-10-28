"""Channel messages are scoped to current members and their authors."""

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


def test_guest_chat_reply_reaction_pin_search_and_moderation():
    owner = APIClient()
    created = owner.post("/communities", {"name": "Calculus"})
    community_id = created.data["id"]
    channel_id = owner.get(f"/communities/{community_id}").data["channels"][0]["id"]
    base = f"/communities/{community_id}/channels/{channel_id}"
    visitor = APIClient()
    assert visitor.get(f"{base}/messages").status_code == 403
    assert visitor.post(f"{base}/messages", {"content": "No"}).status_code == 403
    assert visitor.post(f"/communities/{community_id}/join").status_code == 200

    first = visitor.post(f"{base}/messages", {"content": "When is the exam?"})
    assert first.status_code == 201
    message_id = first.data["id"]
    assert first.data["mine"] is True
    assert owner.get(f"{base}/messages").data["items"][0]["content"] == "When is the exam?"
    assert owner.patch(f"{base}/messages/{message_id}", {"content": "No"}).status_code == 403
    edited = visitor.patch(f"{base}/messages/{message_id}", {"content": "Exam on Friday?"})
    assert edited.status_code == 200
    assert edited.data["edited_at"] is not None
    reply = owner.post(f"{base}/messages", {"content": "Friday at 2", "reply_to": message_id})
    assert reply.status_code == 201
    assert reply.data["reply_to"] == message_id
    assert (
        visitor.post(f"{base}/messages/{message_id}/reactions", {"emoji": "👍"}).status_code == 200
    )
    assert (
        visitor.post(f"{base}/messages/{message_id}/reactions", {"emoji": "👍"}).data["reactions"][
            0
        ]["count"]
        == 1
    )
    assert visitor.post(f"{base}/messages/{message_id}/pin").status_code == 403
    assert owner.post(f"{base}/messages/{message_id}/pin").status_code == 200
    assert owner.get(f"{base}/pins").data["items"][0]["id"] == message_id
    assert (
        visitor.get(f"/communities/{community_id}/messages/search?q=Friday").data["items"][0]["id"]
        == reply.data["id"]
    )
    assert owner.delete(f"{base}/messages/{message_id}").status_code == 204
    deleted = visitor.get(f"{base}/messages").data["items"][0]
    assert deleted["content"] == ""
    assert deleted["deleted_at"] is not None
    assert deleted["reactions"] == []
    assert owner.get(f"{base}/pins").data["items"] == []


def test_message_paging_channel_boundary_and_archiving():
    user = get_user_model().objects.create_user(username="owner", password="test-password")
    client = APIClient()
    client.force_authenticate(user=user)
    community_id = client.post("/communities", {"name": "Algebra"}).data["id"]
    channels = f"/communities/{community_id}/channels"
    general_id = client.get(channels).data[0]["id"]
    other_id = client.post(channels, {"name": "homework"}).data["id"]
    base = f"{channels}/{general_id}/messages"
    ids = [client.post(base, {"content": f"Problem {i}"}).data["id"] for i in range(3)]
    assert [item["id"] for item in client.get(f"{base}?limit=2").data["items"]] == ids[1:]
    assert [item["id"] for item in client.get(f"{base}?before={ids[1]}").data["items"]] == ids[:1]
    assert [item["id"] for item in client.get(f"{base}?after={ids[0]}").data["items"]] == ids[1:]
    assert (
        client.post(
            f"{channels}/{other_id}/messages", {"content": "Cross", "reply_to": ids[0]}
        ).status_code
        == 404
    )
    assert client.patch(f"{channels}/{general_id}", {"archived": True}).status_code == 200
    assert client.post(base, {"content": "Late"}).status_code == 403
    assert len(client.get(base).data["items"]) == 3
