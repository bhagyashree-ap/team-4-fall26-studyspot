"""Channel text chat. Every read and write checks current community membership."""

import hashlib
from typing import cast

from django.contrib.postgres.search import SearchQuery, SearchVector
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.request import Request
from rest_framework.response import Response

from .models import Channel, Community, Message, Reaction
from .permissions import role_for
from .views import CommunityView, community_for, guest_id, viewer


class MessageInput(serializers.Serializer):
    content = serializers.CharField(max_length=2000, trim_whitespace=True)
    reply_to = serializers.IntegerField(min_value=1, required=False)


class ReactionInput(serializers.Serializer):
    emoji = serializers.CharField(max_length=32, trim_whitespace=True)


class MessagePage(serializers.Serializer):
    limit = serializers.IntegerField(default=50, min_value=1, max_value=50)
    before = serializers.IntegerField(min_value=1, required=False)
    after = serializers.IntegerField(min_value=0, required=False)

    def validate(self, attrs):
        if "before" in attrs and "after" in attrs:
            raise serializers.ValidationError("Use before or after, not both.")
        return attrs


def channel_for(community_id: int, channel_id: int) -> Channel:
    community = community_for(community_id)
    try:
        return Channel.objects.get(pk=channel_id, community=community)
    except Channel.DoesNotExist as exc:
        raise NotFound("Channel not found.") from exc


def member_role(request: Request, channel: Channel) -> str:
    community = cast(Community, channel.community)
    role = role_for(community, viewer(request, community))
    if role == "visitor":
        raise PermissionDenied("Join this community to read or send messages.")
    return role


def authenticated(request: Request) -> bool:
    return bool(getattr(request.user, "is_authenticated", False))


def author_name(request: Request) -> str:
    if authenticated(request):
        account = getattr(request.user, "account", None)
        return account.username if account and account.username else request.user.get_username()
    identity = guest_id(request)
    if identity is None:
        raise PermissionDenied("Join this community to send messages.")
    return f"Guest {hashlib.sha256(identity.encode()).hexdigest()[:6]}"


def is_author(request: Request, message: Message) -> bool:
    if authenticated(request):
        return message.author_id == request.user.pk
    identity = guest_id(request)
    return bool(identity and message.guest_id == identity)


def message_data(request: Request, message: Message, role: str) -> dict:
    identity = guest_id(request)
    reactions = {}
    for reaction in message.reactions.all():
        entry = reactions.setdefault(
            reaction.emoji, {"emoji": reaction.emoji, "count": 0, "me": False}
        )
        entry["count"] += 1
        if (
            reaction.user_id == request.user.pk
            if authenticated(request)
            else bool(identity and reaction.guest_id == identity)
        ):
            entry["me"] = True
    return {
        "id": message.pk,
        "channel_id": message.channel_id,
        "author_name": message.author_name,
        "content": message.content,
        "reply_to": message.reply_to_id,
        "created_at": message.created_at,
        "edited_at": message.edited_at,
        "deleted_at": message.deleted_at,
        "pinned_at": message.pinned_at,
        "reactions": list(reactions.values()),
        "mine": is_author(request, message),
        "can_delete": is_author(request, message) or role in {"owner", "moderator"},
    }


def message_for(channel: Channel, message_id: int) -> Message:
    try:
        return Message.objects.get(pk=message_id, channel=channel)
    except Message.DoesNotExist as exc:
        raise NotFound("Message not found.") from exc


class Messages(CommunityView):
    def get(self, request: Request, community_id: int, channel_id: int) -> Response:
        channel = channel_for(community_id, channel_id)
        role = member_role(request, channel)
        parsed = MessagePage(data=request.query_params)
        parsed.is_valid(raise_exception=True)
        data = parsed.validated_data
        query = Message.objects.filter(channel=channel).prefetch_related("reactions")
        if "after" in data:
            query = query.filter(pk__gt=data["after"]).order_by("id")
        else:
            if "before" in data:
                query = query.filter(pk__lt=data["before"])
            query = query.order_by("-id")
        found = list(query[: data["limit"] + 1])
        items = found[: data["limit"]]
        if "after" not in data:
            items.reverse()
        return Response(
            {
                "items": [message_data(request, item, role) for item in items],
                "has_more": len(found) > data["limit"],
            }
        )

    def post(self, request: Request, community_id: int, channel_id: int) -> Response:
        channel = channel_for(community_id, channel_id)
        role = member_role(request, channel)
        if channel.archived:
            raise PermissionDenied("This channel is archived.")
        parsed = MessageInput(data=request.data)
        parsed.is_valid(raise_exception=True)
        reply_id = parsed.validated_data.get("reply_to")
        if (
            reply_id
            and not Message.objects.filter(
                pk=reply_id, channel=channel, deleted_at__isnull=True
            ).exists()
        ):
            raise NotFound("Reply target not found in this channel.")
        message = Message.objects.create(
            channel=channel,
            author=request.user if authenticated(request) else None,
            guest_id="" if authenticated(request) else guest_id(request) or "",
            author_name=author_name(request),
            content=parsed.validated_data["content"],
            reply_to_id=reply_id,
        )
        return Response(message_data(request, message, role), status=201)


class MessageDetail(CommunityView):
    def patch(
        self, request: Request, community_id: int, channel_id: int, message_id: int
    ) -> Response:
        channel = channel_for(community_id, channel_id)
        role = member_role(request, channel)
        message = message_for(channel, message_id)
        if message.deleted_at:
            raise NotFound("Message not found.")
        if not is_author(request, message):
            raise PermissionDenied("Only the author can edit this message.")
        parsed = MessageInput(data=request.data)
        parsed.is_valid(raise_exception=True)
        message.content = parsed.validated_data["content"]
        message.edited_at = timezone.now()
        message.save(update_fields=["content", "edited_at"])
        return Response(message_data(request, message, role))

    def delete(
        self, request: Request, community_id: int, channel_id: int, message_id: int
    ) -> Response:
        channel = channel_for(community_id, channel_id)
        role = member_role(request, channel)
        message = message_for(channel, message_id)
        if not is_author(request, message) and role not in {"owner", "moderator"}:
            raise PermissionDenied("Only the author or a moderator can delete this message.")
        if message.deleted_at is None:
            message.content = ""
            message.deleted_at = timezone.now()
            message.pinned_at = None
            message.save(update_fields=["content", "deleted_at", "pinned_at"])
            Reaction.objects.filter(message=message).delete()
        return Response(status=204)


class MessagePin(CommunityView):
    def post(
        self, request: Request, community_id: int, channel_id: int, message_id: int
    ) -> Response:
        return self.set_pin(request, community_id, channel_id, message_id, True)

    def delete(
        self, request: Request, community_id: int, channel_id: int, message_id: int
    ) -> Response:
        return self.set_pin(request, community_id, channel_id, message_id, False)

    def set_pin(
        self, request: Request, community_id: int, channel_id: int, message_id: int, pinned: bool
    ) -> Response:
        channel = channel_for(community_id, channel_id)
        role = member_role(request, channel)
        if role not in {"owner", "moderator"}:
            raise PermissionDenied("Only owners and moderators can pin messages.")
        message = message_for(channel, message_id)
        if message.deleted_at:
            raise NotFound("Message not found.")
        Message.objects.filter(pk=message.pk).update(pinned_at=timezone.now() if pinned else None)
        message.refresh_from_db(fields=["pinned_at"])
        return Response(message_data(request, message, role))


class Pins(CommunityView):
    def get(self, request: Request, community_id: int, channel_id: int) -> Response:
        channel = channel_for(community_id, channel_id)
        role = member_role(request, channel)
        messages = (
            Message.objects.filter(
                channel=channel, pinned_at__isnull=False, deleted_at__isnull=True
            )
            .order_by("-pinned_at")
            .prefetch_related("reactions")[:50]
        )
        return Response({"items": [message_data(request, item, role) for item in messages]})


class MessageReactions(CommunityView):
    def post(
        self, request: Request, community_id: int, channel_id: int, message_id: int
    ) -> Response:
        channel = channel_for(community_id, channel_id)
        role = member_role(request, channel)
        message = message_for(channel, message_id)
        if message.deleted_at:
            raise NotFound("Message not found.")
        parsed = ReactionInput(data=request.data)
        parsed.is_valid(raise_exception=True)
        emoji = parsed.validated_data["emoji"]
        actor = (
            {"user": request.user} if authenticated(request) else {"guest_id": guest_id(request)}
        )
        try:
            with transaction.atomic():
                Reaction.objects.get_or_create(message=message, emoji=emoji, **actor)
        except IntegrityError:
            pass  # A concurrent identical reaction has already been recorded.
        message = Message.objects.prefetch_related("reactions").get(pk=message.pk)
        return Response(message_data(request, message, role))

    def delete(
        self, request: Request, community_id: int, channel_id: int, message_id: int, emoji: str
    ) -> Response:
        channel = channel_for(community_id, channel_id)
        role = member_role(request, channel)
        message = message_for(channel, message_id)
        actor = (
            {"user": request.user} if authenticated(request) else {"guest_id": guest_id(request)}
        )
        Reaction.objects.filter(message=message, emoji=emoji, **actor).delete()
        message = Message.objects.prefetch_related("reactions").get(pk=message.pk)
        return Response(message_data(request, message, role))


class MessageSearch(CommunityView):
    def get(self, request: Request, community_id: int) -> Response:
        community = community_for(community_id)
        role = role_for(community, viewer(request, community))
        if role == "visitor":
            raise PermissionDenied("Join this community to search messages.")
        query = request.query_params.get("q", "").strip()
        if not 2 <= len(query) <= 100:
            raise serializers.ValidationError({"q": "Use 2 to 100 characters."})
        found = (
            Message.objects.filter(channel__community=community, deleted_at__isnull=True)
            .annotate(search=SearchVector("content", config="english"))
            .filter(search=SearchQuery(query, config="english", search_type="websearch"))
            .order_by("-id")
            .prefetch_related("reactions")[:50]
        )
        return Response({"items": [message_data(request, item, role) for item in found]})
