"""Private groups share messaging behavior while restricting access to participants."""

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from communities.models import DirectConversation

pytestmark = pytest.mark.django_db


def participants(community_id):
    result = []
    for username in ("MayaGroup", "JordanGroup"):
        user = get_user_model().objects.create_user(username=username)
        client = APIClient()
        client.force_authenticate(user=user)
        assert client.post(f"/communities/{community_id}/join").status_code == 200
        result.append((user, client))
    return result


def group_payload(community_id, users):
    return {
        "name": "Thursday study crew",
        "participants": [
            {"community_id": community_id, "target": {"user_id": str(user.pk)}} for user, _ in users
        ],
    }


def test_group_is_private_and_messages_have_per_person_unread_counts(existing_guest_community):
    owner, community_id = existing_guest_community
    users = participants(community_id)
    response = owner.post("/dms", group_payload(community_id, users), format="json")
    assert response.status_code == 201
    group = response.data
    assert group["kind"] == "group"
    assert group["member_count"] == 3
    assert group["other_name"] == "Thursday study crew"
    path = f"/dms/{group['id']}"
    sender = users[0][1]
    assert sender.get("/dms").data["items"][0]["id"] == group["id"]
    sent = sender.post(path + "/messages", {"content": "Bring your notes."})
    assert sent.status_code == 201
    assert owner.get("/dms").data["items"][0]["unread_count"] == 1
    assert sender.get("/dms").data["items"][0]["unread_count"] == 0
    assert any(
        item.get("conversation_id") == group["id"]
        for item in owner.get("/chat/notifications").data["items"]
    )
    outsider = APIClient()
    outsider.force_authenticate(user=get_user_model().objects.create_user(username="outsider"))
    assert outsider.get(path).status_code == 404
    assert outsider.get(path + "/messages").status_code == 404
    assert outsider.post(path + "/messages", {"content": "Not invited"}).status_code == 404
    assert outsider.get("/dms").data["items"] == []
    assert outsider.get("/chat/notifications").data["items"] == []


def test_read_through_marks_only_loaded_messages_and_does_not_regress(existing_guest_community):
    owner, community_id = existing_guest_community
    users = participants(community_id)
    started = owner.post(f"/communities/{community_id}/dms", {"user_id": str(users[0][0].pk)})
    path = f"/dms/{started.data['id']}"
    sender = users[0][1]
    first = sender.post(path + "/messages", {"content": "First"}).data["id"]
    second = sender.post(path + "/messages", {"content": "Second"}).data["id"]
    owner.post(path + "/messages", {"content": "My own message"})
    assert owner.get("/dms").data["items"][0]["unread_count"] == 2
    assert owner.put(path + "/read", {"read_through": first}).status_code == 200
    assert owner.get(path).data["unread_count"] == 1
    assert owner.put(path + "/read", {"read_through": second}).status_code == 200
    assert owner.put(path + "/read", {"read_through": first}).data["last_read"] == second
    assert owner.get(path).data["unread_count"] == 0
    owner.put(path + "/read", {"unread_from": second})
    assert owner.get(path).data["unread_count"] == 1
    assert sender.delete(path + f"/messages/{second}").status_code == 204
    assert owner.get(path).data["unread_count"] == 0
    assert owner.put(path + "/read", {"read_through": 999999}).status_code == 404
    assert (
        owner.put(path + "/read", {"read_through": first, "unread_from": first}).status_code == 422
    )


@pytest.mark.parametrize("case", ["duplicate", "not_shared", "too_few", "blank_name"])
def test_invalid_groups_leave_no_partial_conversation(existing_guest_community, case):
    owner, community_id = existing_guest_community
    users = participants(community_id)
    payload = group_payload(community_id, users)
    expected = 422
    if case == "duplicate":
        payload["participants"][1] = payload["participants"][0]
    elif case == "not_shared":
        outsider = get_user_model().objects.create_user(username="not-in-the-community")
        payload["participants"][1]["target"] = {"user_id": str(outsider.pk)}
        expected = 404
    elif case == "too_few":
        payload["participants"] = payload["participants"][:1]
    else:
        payload["name"] = " "
    count = DirectConversation.objects.count()
    assert owner.post("/dms", payload, format="json").status_code == expected
    assert DirectConversation.objects.count() == count
