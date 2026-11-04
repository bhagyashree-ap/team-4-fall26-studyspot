"""Public chat contracts shared by channel members and DM participants."""

import base64
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


@pytest.fixture
def members(existing_guest_community):
    owner, community = existing_guest_community
    member = APIClient()
    member.post(f"/communities/{community}/join")
    channels = f"/communities/{community}/channels"
    channel = f"{channels}/{owner.get(channels).data[0]['id']}"
    return owner, member, channel


@pytest.fixture(params=["channel", "dm"])
def room(request, members):
    owner, member, channel = members
    if request.param == "channel":
        return members
    target = member.post(f"{channel}/messages", {"content": "Hello"}).data["id"]
    conversation = owner.post(f"{channel}/messages/{target}/dm").data["id"]
    return owner, member, f"/dms/{conversation}"


def test_thread_partition_and_page_boundaries(room):
    owner, member, base = room
    url = base + "/messages"
    root = owner.post(url, {"content": "Topic"}).data["id"]
    replies = [member.post(url, {"content": str(i), "thread": root}).data["id"] for i in range(4)]
    page = member.get(url, {"thread": root, "limit": 2}).data
    older = member.get(url, {"thread": root, "before": page["items"][0]["id"], "limit": 2}).data
    assert page["has_more"] and not older["has_more"]
    assert [item["id"] for item in older["items"] + page["items"]] == replies
    assert [item["id"] for item in member.get(url).data["items"]] == [root]
    assert member.get(f"{url}/{replies[1]}").data["content"] == "1"
    assert member.post(url, {"content": "nested", "thread": replies[0]}).status_code == 404


def test_ballot_counts_distinct_voters_and_preserves_last_valid_vote(room):
    first, second, base = room
    url = base + "/messages"
    for invalid in (["one"], ["one", "one"], [str(i) for i in range(11)]):
        assert (
            first.post(url, {"content": "Choose", "options": invalid}, format="json").status_code
            == 422
        )
    poll = first.post(url, {"content": "Choose", "options": ["A", "B"]}, format="json").data
    vote = f"{url}/{poll['id']}/vote"
    for voter, choice, counts in [
        (first, 0, [1, 0]),
        (first, 0, [1, 0]),
        (second, 1, [1, 1]),
        (first, 1, [0, 2]),
    ]:
        result = voter.put(vote, {"choice": choice}).data
        assert result["counts"] == counts
        assert result["mine"] == choice
    assert first.put(vote, {"choice": 2}).status_code == 422
    assert second.get(f"{url}/{poll['id']}").data["poll"]["counts"] == [0, 2]


def test_attachment_limit_roundtrip_and_revocation(room):
    owner, member, base = room
    url = base + "/messages"
    limit = 2 * 1024 * 1024
    data = bytes(range(256)) * (limit // 256)
    assert owner.post(url, {"file": SimpleUploadedFile("big.mp4", data + b"x")}).status_code == 422
    message = owner.post(url, {"file": SimpleUploadedFile("video.mp4", data)}).data
    attachment = f"{url}/{message['id']}?attachment=1"
    assert APIClient().get(attachment).status_code in {403, 404}
    assert base64.b64decode(member.get(attachment).data["data"]) == data
    assert owner.delete(f"{url}/{message['id']}").status_code == 204
    assert member.get(attachment).status_code == 404


def test_typing_excludes_self_and_expires_at_deadline(room):
    owner, member, base = room
    presence = base + "/presence"
    start = datetime.now(UTC)
    with patch("django.utils.timezone.now", return_value=start):
        owner.post(presence, {"typing": True})
        assert owner.get(presence).data["typing"] == []
        assert len(member.get(presence).data["typing"]) == 1
    with patch("django.utils.timezone.now", return_value=start + timedelta(seconds=7)):
        assert member.get(presence).data["typing"] == []


def test_search_intersects_sender_date_and_keyword_and_excludes_deleted(room):
    owner, member, base = room
    url = base + "/messages"
    search = base.split("/channels/")[0] + "/messages/search"
    midnight = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    with patch("django.utils.timezone.now", return_value=midnight - timedelta(microseconds=1)):
        owner.post(url, {"content": "exam"})
    with patch("django.utils.timezone.now", return_value=midnight):
        wanted = owner.post(url, {"content": "exam schedule"}).data
        owner.post(url, {"content": "lunch"})
        member.post(url, {"content": "exam"})
    filters = {"q": "exam", "sender": wanted["author_name"], "date": midnight.date().isoformat()}
    assert [m["id"] for m in member.get(search, filters).data["items"]] == [wanted["id"]]
    owner.delete(f"{url}/{wanted['id']}")
    assert member.get(search, filters).data["items"] == []


def test_channel_mentions_respect_visibility_read_cursor_and_alert_mode(members):
    owner, member, base = members
    url = base + "/messages"
    me = member.post(url, {"content": "Hello"}).data["author_name"]
    member.put(base + "/alerts", {"alerts": "mentions"})

    def inbox():
        return {row["id"] for row in member.get("/chat/notifications").data["items"]}

    def post(text):
        return owner.post(url, {"content": text}).data["id"]

    post("ordinary text")
    with patch("django.utils.timezone.now", return_value=datetime.now(UTC) + timedelta(seconds=66)):
        post("@here")
    assert not inbox()
    member.put(base + "/read", {})
    member.post(base + "/presence", {})
    ids = [post(token) for token in [f"@[{me}]", "@member", "@everyone", "@here"]]
    post("@owner")
    assert inbox() == set(ids)
    assert member.post(url, {"content": "@everyone"}).status_code == 403
    member.put(base + "/read", {})
    assert inbox() == set()
    member.put(base + "/read", {"unread_from": ids[-2]})
    assert inbox() == set(ids[-2:])
    member.put(base + "/alerts", {"alerts": "muted"})
    assert inbox() == set()
    member.put(base + "/alerts", {"alerts": "all"})
    owner.patch(base, {"private": True})
    assert inbox() == set()
    assert member.get(f"{url}/{ids[-1]}").status_code == 404


def test_channel_metadata_changes_require_owner_and_preserve_links(members):
    owner, member, base = members
    assert member.patch(base, {"topic": "unauthorized"}).status_code == 401
    assert owner.patch(base, {"name": "exam-prep", "topic": "x" * 256}).status_code == 200
    assert owner.patch(base, {"topic": "x" * 257}).status_code == 422
    channel = next(
        ch for ch in member.get(base.rsplit("/", 1)[0]).data if base.endswith("/" + str(ch["id"]))
    )
    assert (channel["name"], channel["topic"]) == ("exam-prep", "x" * 256)


def test_direct_reactions_and_pins_are_idempotent_and_participant_only(members):
    first, second, channel = members
    posted = second.post(channel + "/messages", {"content": "Start"}).data["id"]
    conversation = first.post(f"{channel}/messages/{posted}/dm").data["id"]
    base = f"/dms/{conversation}"
    message = first.post(base + "/messages", {"content": "Pin this"}).data["id"]
    target = f"{base}/messages/{message}"
    outsider = APIClient()
    outsider.post(channel.split("/channels")[0] + "/join")
    assert outsider.put(target + "/pin", {"pinned": True}).status_code == 404
    for client in (first, first, second):
        client.put(target + "/reactions", {"emoji": "🎉", "active": True})
        client.put(target + "/pin", {"pinned": True})
    assert second.get(target).data["reactions"] == [{"emoji": "🎉", "count": 2, "me": True}]
    assert [m["id"] for m in first.get(base + "/pins").data["items"]] == [message]
    for _ in range(2):
        first.put(target + "/reactions", {"emoji": "🎉", "active": False})
    assert first.get(target).data["reactions"] == [{"emoji": "🎉", "count": 1, "me": False}]
    first.delete(target)
    assert second.get(base + "/pins").data["items"] == []
    assert second.get(target).data["reactions"] == []


def test_demo_guest_keeps_the_same_name_in_chat_roster_and_dm(settings, members):
    settings.DEBUG = True
    settings.CHAT_GUEST_DEMO = True
    owner, guest, channel = members
    message = guest.post(channel + "/messages", {"content": "See you at the library"}).data
    name = message["author_name"]
    assert len(name.split()) == 2 and not name.startswith("Guest ")
    roster = owner.get(channel.split("/channels")[0] + "/members").data["guest_items"]
    assert name in {member["display_name"] for member in roster}
    assert owner.post(f"{channel}/messages/{message['id']}/dm").data["other_name"] == name
