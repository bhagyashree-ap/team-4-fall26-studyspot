"""Private one-to-one text conversations for account and session guests."""

import hashlib

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.request import Request
from rest_framework.response import Response

from .message_views import (
    MessageInput,
    MessagePage,
    authenticated,
    author_name,
    channel_for,
    member_role,
)
from .models import DirectConversation, DirectMessage, GuestMembership, Membership, Message
from .permissions import role_for
from .views import CommunityView, community_for, guest_id, user_id_for, viewer


def person_key(request: Request) -> str | None:
    if authenticated(request):
        return f"u:{request.user.pk}"
    identity = guest_id(request)
    return f"g:{identity}" if identity else None


def conversation_data(conversation: DirectConversation, key: str) -> dict:
    return {
        "id": conversation.pk,
        "other_name": conversation.second_name
        if key == conversation.first_key
        else conversation.first_name,
        "updated_at": conversation.updated_at,
    }


def direct_message_data(message: DirectMessage, key: str) -> dict:
    return {
        "id": message.pk,
        "author_name": message.author_name,
        "content": message.content,
        "reply_to": message.reply_to_id,
        "created_at": message.created_at,
        "edited_at": message.edited_at,
        "deleted_at": message.deleted_at,
        "mine": message.sender_key == key,
    }


def conversation_for(request: Request, conversation_id: int) -> tuple[DirectConversation, str]:
    key = person_key(request)
    if key is None:
        raise PermissionDenied("Join a community to use direct messages.")
    try:
        return DirectConversation.objects.get(
            Q(first_key=key) | Q(second_key=key), pk=conversation_id
        ), key
    except DirectConversation.DoesNotExist as exc:
        raise NotFound("Conversation not found.") from exc


def start(request: Request, target_key: str, target_name: str) -> Response:
    key = person_key(request)
    if key is None or key == target_key:
        raise PermissionDenied("Choose another community member to message.")
    first, second = sorted((key, target_key))
    digest = hashlib.sha256(f"{first}\0{second}".encode()).hexdigest()
    own_name = author_name(request)
    conversation, _ = DirectConversation.objects.get_or_create(
        pair_key=digest,
        defaults={
            "first_key": first,
            "second_key": second,
            "first_name": own_name if first == key else target_name,
            "second_name": target_name if first == key else own_name,
        },
    )
    return Response(conversation_data(conversation, key), status=201)


class StartFromMessage(CommunityView):
    def post(
        self, request: Request, community_id: int, channel_id: int, message_id: int
    ) -> Response:
        channel = channel_for(community_id, channel_id)
        member_role(request, channel)
        try:
            message = Message.objects.get(pk=message_id, channel=channel, deleted_at__isnull=True)
        except Message.DoesNotExist as exc:
            raise NotFound("Message not found.") from exc
        if message.author_id is not None:
            still_member = (
                channel.community.owner_id == message.author_id
                or Membership.objects.filter(
                    community=channel.community, user_id=message.author_id
                ).exists()
            )
            target_key = f"u:{message.author_id}"
        else:
            still_member = GuestMembership.objects.filter(
                community=channel.community,
                guest_id=message.guest_id,
                expires_at__gt=timezone.now(),
            ).exists()
            target_key = f"g:{message.guest_id}"
        if not still_member:
            raise PermissionDenied("This person is no longer a community member.")
        return start(request, target_key, message.author_name)


class StartFromMember(CommunityView):
    def post(self, request: Request, community_id: int) -> Response:
        community = community_for(community_id)
        if role_for(community, viewer(request, community)) == "visitor":
            raise PermissionDenied("Join this community to use direct messages.")

        class Target(serializers.Serializer):
            user_id = serializers.CharField(max_length=64, required=False)
            guest_member_id = serializers.IntegerField(min_value=1, required=False)

            def validate(self, attrs):
                if len(attrs) != 1:
                    raise serializers.ValidationError("Choose one community member.")
                return attrs

        parsed = Target(data=request.data)
        parsed.is_valid(raise_exception=True)
        if "guest_member_id" in parsed.validated_data:
            guest = GuestMembership.objects.filter(
                pk=parsed.validated_data["guest_member_id"],
                community=community,
                expires_at__gt=timezone.now(),
            ).first()
            if guest is None:
                raise NotFound("Community member not found.")
            target_name = f"Guest {hashlib.sha256(guest.guest_id.encode()).hexdigest()[:6]}"
            return start(request, f"g:{guest.guest_id}", target_name)
        user_id = user_id_for(parsed.validated_data["user_id"])
        if (
            community.owner_id != user_id
            and not Membership.objects.filter(community=community, user_id=user_id).exists()
        ):
            raise NotFound("Community member not found.")
        target = get_user_model().objects.get(pk=user_id)
        account = getattr(target, "account", None)
        target_name = account.username if account and account.username else target.get_username()
        return start(request, f"u:{user_id}", target_name)


class DirectConversations(CommunityView):
    def get(self, request: Request) -> Response:
        key = person_key(request)
        if key is None:
            return Response({"items": []})
        found = DirectConversation.objects.filter(Q(first_key=key) | Q(second_key=key)).order_by(
            "-updated_at", "-id"
        )[:50]
        return Response({"items": [conversation_data(item, key) for item in found]})


class DirectMessages(CommunityView):
    def get(self, request: Request, conversation_id: int) -> Response:
        conversation, key = conversation_for(request, conversation_id)
        parsed = MessagePage(data=request.query_params)
        parsed.is_valid(raise_exception=True)
        data = parsed.validated_data
        query = DirectMessage.objects.filter(conversation=conversation)
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
                "items": [direct_message_data(item, key) for item in items],
                "has_more": len(found) > data["limit"],
            }
        )

    def post(self, request: Request, conversation_id: int) -> Response:
        conversation, key = conversation_for(request, conversation_id)
        parsed = MessageInput(data=request.data)
        parsed.is_valid(raise_exception=True)
        reply_id = parsed.validated_data.get("reply_to")
        if (
            reply_id
            and not DirectMessage.objects.filter(
                pk=reply_id, conversation=conversation, deleted_at__isnull=True
            ).exists()
        ):
            raise NotFound("Reply target not found in this conversation.")
        message = DirectMessage.objects.create(
            conversation=conversation,
            sender_key=key,
            author_name=author_name(request),
            content=parsed.validated_data["content"],
            reply_to_id=reply_id,
        )
        DirectConversation.objects.filter(pk=conversation.pk).update(updated_at=timezone.now())
        return Response(direct_message_data(message, key), status=201)


class DirectMessageDetail(CommunityView):
    def patch(self, request: Request, conversation_id: int, message_id: int) -> Response:
        conversation, key = conversation_for(request, conversation_id)
        try:
            message = DirectMessage.objects.get(
                pk=message_id, conversation=conversation, deleted_at__isnull=True
            )
        except DirectMessage.DoesNotExist as exc:
            raise NotFound("Message not found.") from exc
        if message.sender_key != key:
            raise PermissionDenied("Only the author can edit this message.")
        parsed = MessageInput(data=request.data)
        parsed.is_valid(raise_exception=True)
        message.content = parsed.validated_data["content"]
        message.edited_at = timezone.now()
        message.save(update_fields=["content", "edited_at"])
        return Response(direct_message_data(message, key))

    def delete(self, request: Request, conversation_id: int, message_id: int) -> Response:
        conversation, key = conversation_for(request, conversation_id)
        try:
            message = DirectMessage.objects.get(pk=message_id, conversation=conversation)
        except DirectMessage.DoesNotExist as exc:
            raise NotFound("Message not found.") from exc
        if message.sender_key != key:
            raise PermissionDenied("Only the author can delete this message.")
        if message.deleted_at is None:
            message.content = ""
            message.deleted_at = timezone.now()
            message.save(update_fields=["content", "deleted_at"])
        return Response(status=204)
