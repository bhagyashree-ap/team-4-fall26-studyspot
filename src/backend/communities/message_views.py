"""Channel text chat. Every read and write checks current community membership."""

import base64
from datetime import UTC
from math import ceil
from typing import cast

from django.contrib.postgres.search import SearchQuery, SearchVector
from django.db import IntegrityError, transaction
from django.db.models.functions import TruncDate
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import NotFound, PermissionDenied, Throttled
from rest_framework.request import Request
from rest_framework.response import Response

from .guest_names import guest_name
from .mentions import targets
from .models import Channel, Community, Message, Poll, Reaction
from .permissions import role_for
from .views import CommunityView, community_for, guest_id, viewer, visible_channels


class MessageInput(serializers.Serializer):
    content = serializers.CharField(max_length=2000, trim_whitespace=True)
    reply_to = serializers.IntegerField(min_value=1, required=False)


class ReactionInput(serializers.Serializer):
    emoji = serializers.CharField(max_length=32, trim_whitespace=True)


class NewMessageInput(MessageInput):
    options = serializers.ListField(
        child=serializers.CharField(max_length=80), min_length=2, max_length=10, required=False
    )
    thread = serializers.IntegerField(min_value=1, required=False)
    content = serializers.CharField(max_length=2000, required=False, allow_blank=True, default="")
    file = serializers.FileField(required=False, max_length=255)

    def validate(self, attrs):
        upload = attrs.get("file")
        if upload and upload.size > 2 * 1024 * 1024:
            raise serializers.ValidationError("Attachments must be 2 MiB or smaller.")
        if "options" in attrs and (
            not attrs["content"] or len(set(attrs["options"])) != len(attrs["options"])
        ):
            raise serializers.ValidationError("Enter a poll question and distinct choices.")
        if not upload and not attrs["content"]:
            raise serializers.ValidationError("Enter a message or attach a file.")
        return attrs


def thread_root(messages, data):
    root_id = data.get("thread")
    if (
        root_id
        and not messages.filter(
            pk=root_id, thread_root__isnull=True, deleted_at__isnull=True
        ).exists()
    ):
        raise NotFound("Thread starter unavailable.")
    return root_id


def upload_fields(data):
    upload = data.get("file")
    return {"file_name": upload.name, "file_bytes": upload.read()} if upload else {}


def poll_fields(data):
    return {"poll": Poll.objects.create(options=data["options"])} if "options" in data else {}


def poll_data(message, key):
    if not message.poll_id or message.deleted_at:
        return None
    counts = [0] * len(message.poll.options)
    mine = None
    for vote in message.poll.votes.all():
        counts[vote.choice] += 1
        if vote.actor == key:
            mine = vote.choice
    return {"options": message.poll.options, "counts": counts, "mine": mine}


def download(message):
    if message.deleted_at or not message.file_name:
        raise NotFound("Attachment unavailable.")
    return Response(
        {"name": message.file_name, "data": base64.b64encode(message.file_bytes).decode("ascii")}
    )


class MessagePage(serializers.Serializer):
    thread = serializers.IntegerField(min_value=1, required=False)
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
    if channel.private and role not in {"owner", "moderator"}:
        raise NotFound("Channel not found.")
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
    return guest_name(identity)


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
        "thread_root": message.thread_root_id,
        "author_name": message.author_name,
        "content": message.content,
        "poll": poll_data(
            message, f"u:{request.user.pk}" if authenticated(request) else f"g:{identity}"
        ),
        "file_name": "" if message.deleted_at else message.file_name,
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
        query = Message.objects.filter(
            channel=channel, thread_root_id=data.get("thread")
        ).prefetch_related("reactions")
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

    @transaction.atomic
    def post(self, request: Request, community_id: int, channel_id: int) -> Response:
        # ID cursors depend on sends committing in order within each room.
        channel = get_object_or_404(
            Channel.objects.select_for_update(), community_id=community_id, pk=channel_id
        )
        role = member_role(request, channel)
        if channel.read_only and role == "member":
            raise PermissionDenied("This channel is read-only.")
        if channel.archived:
            raise PermissionDenied("This channel is archived.")
        parsed = NewMessageInput(data=request.data)
        parsed.is_valid(raise_exception=True)
        reply_id = parsed.validated_data.get("reply_to")
        if (
            reply_id
            and not Message.objects.filter(
                pk=reply_id, channel=channel, deleted_at__isnull=True
            ).exists()
        ):
            raise NotFound("Reply target not found in this channel.")
        if channel.slowmode_seconds and role == "member":
            previous = (
                channel.messages.filter(author=request.user)
                if authenticated(request)
                else channel.messages.filter(guest_id=guest_id(request))
            )
            latest = previous.order_by("-id").values_list("created_at", flat=True).first()
            if latest:
                remaining = channel.slowmode_seconds - (timezone.now() - latest).total_seconds()
                if remaining > 0:
                    raise Throttled(wait=ceil(remaining), detail="Slowmode is enabled.")
        message = Message.objects.create(
            channel=channel,
            mentions=targets(parsed.validated_data["content"], channel=channel, role=role),
            thread_root_id=thread_root(channel.messages, parsed.validated_data),
            **poll_fields(parsed.validated_data),
            **upload_fields(parsed.validated_data),
            author=request.user if authenticated(request) else None,
            guest_id="" if authenticated(request) else guest_id(request) or "",
            author_name=author_name(request),
            content=parsed.validated_data["content"],
            reply_to_id=reply_id,
        )
        return Response(message_data(request, message, role), status=201)


class MessageDetail(CommunityView):
    def get(
        self, request: Request, community_id: int, channel_id: int, message_id: int
    ) -> Response:
        channel = channel_for(community_id, channel_id)
        role = member_role(request, channel)
        message = message_for(channel, message_id)
        if "attachment" in request.query_params:
            return download(message)
        return Response(message_data(request, message, role))

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
            message.file_bytes = None
            message.file_name = ""
            message.save(
                update_fields=["content", "deleted_at", "pinned_at", "file_name", "file_bytes"]
            )
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
        messages = Message.objects.filter(channel__in=visible_channels(community, role))
        found = search_messages(messages, request.query_params).prefetch_related("reactions")
        return Response({"items": [message_data(request, item, role) for item in found]})


def search_messages(messages, params):
    class Filters(serializers.Serializer):
        q = serializers.CharField(min_length=2, max_length=100, required=False)
        sender = serializers.CharField(max_length=150, required=False)
        date = serializers.DateField(required=False)

    parsed = Filters(data=params)
    parsed.is_valid(raise_exception=True)
    filters = parsed.validated_data
    if not filters:
        raise serializers.ValidationError("Enter a keyword, sender or date.")
    found = messages.filter(deleted_at__isnull=True)
    if "q" in filters:
        found = found.annotate(search=SearchVector("content", config="english")).filter(
            search=SearchQuery(filters["q"], config="english", search_type="websearch")
        )
    if "sender" in filters:
        found = found.filter(author_name__iexact=filters["sender"])
    if "date" in filters:
        found = found.alias(utc_day=TruncDate("created_at", tzinfo=UTC)).filter(
            utc_day=filters["date"]
        )
    return found.order_by("-id")[:50]
