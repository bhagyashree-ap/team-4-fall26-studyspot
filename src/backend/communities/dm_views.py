"""Private one-to-one text conversations for account and session guests."""

import hashlib
import secrets

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, Exists, F, OuterRef, Q, Subquery, Value
from django.db.models.functions import Coalesce, NullIf
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.request import Request
from rest_framework.response import Response

from .guest_names import guest_name
from .mentions import targets
from .message_views import (
    MessageInput,
    MessagePage,
    NewMessageInput,
    ReactionInput,
    authenticated,
    author_name,
    channel_for,
    download,
    member_role,
    poll_data,
    poll_fields,
    search_messages,
    thread_root,
    upload_fields,
)
from .models import (
    Community,
    ConversationParticipant,
    ConversationPreference,
    DirectConversation,
    DirectMessage,
    DirectReaction,
    GuestMembership,
    Membership,
    Message,
    RoomMemberState,
)
from .permissions import role_for
from .views import CommunityView, community_for, guest_id, user_id_for, viewer


def person_key(request: Request) -> str | None:
    if authenticated(request):
        return f"u:{request.user.pk}"
    identity = guest_id(request)
    return f"g:{identity}" if identity else None


def unread_counts(key: str, ids: list[int]) -> dict[int, int]:
    state = RoomMemberState.objects.filter(actor=key, conversation_id=OuterRef("conversation_id"))
    rows = (
        DirectMessage.objects.filter(conversation_id__in=ids, deleted_at__isnull=True)
        .exclude(sender_key=key)
        .annotate(cursor=Coalesce(Subquery(state.values("last_read")[:1]), Value(0)))
        .filter(pk__gt=F("cursor"))
        .values("conversation_id")
        .annotate(total=Count("id"))
    )
    return {row["conversation_id"]: row["total"] for row in rows}


def visible_conversations(key: str):
    groups = ConversationParticipant.objects.filter(actor=key, conversation__kind="group")
    removed = ConversationPreference.objects.filter(
        conversation_id=OuterRef("pk"), actor=key, deleted=True
    )
    return DirectConversation.objects.filter(
        Q(first_key=key) | Q(second_key=key) | Q(pk__in=groups.values("conversation_id"))
    ).exclude(Exists(removed))


def conversation_data(
    conversation: DirectConversation,
    key: str,
    unread_count: int | None = None,
    pinned: bool = False,
) -> dict:
    group = conversation.kind == DirectConversation.Kind.GROUP
    name = (
        conversation.name
        if group
        else (
            conversation.second_name if key == conversation.first_key else conversation.first_name
        )
    )
    members = list(conversation.participants.all()) if group else []
    return {
        "id": conversation.pk,
        "kind": conversation.kind,
        "other_name": name,
        "member_count": len(members) if group else 2,
        "member_names": [member.name for member in members if member.actor != key]
        if group
        else [name],
        "updated_at": conversation.updated_at,
        "unread_count": unread_counts(key, [conversation.pk]).get(conversation.pk, 0)
        if unread_count is None
        else unread_count,
        "pinned": pinned,
    }


def direct_message_data(message: DirectMessage, key: str) -> dict:
    reactions = {}
    if not message.deleted_at:
        for reaction in message.reactions.all():
            item = reactions.setdefault(
                reaction.emoji, {"emoji": reaction.emoji, "count": 0, "me": False}
            )
            item["count"] += 1
            item["me"] |= reaction.actor == key
    return {
        "id": message.pk,
        "author_name": message.author_name,
        "content": message.content,
        "poll": poll_data(message, key),
        "file_name": "" if message.deleted_at else message.file_name,
        "reply_to": message.reply_to_id,
        "thread_root": message.thread_root_id,
        "created_at": message.created_at,
        "edited_at": message.edited_at,
        "deleted_at": message.deleted_at,
        "reactions": list(reactions.values()),
        "pinned_at": message.pinned_at,
        "mine": message.sender_key == key,
    }


def conversation_for(request: Request, conversation_id: int) -> tuple[DirectConversation, str]:
    key = person_key(request)
    if key is None:
        raise PermissionDenied("Join a community to use direct messages.")
    try:
        return visible_conversations(key).get(pk=conversation_id), key
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


class PeopleSearch(CommunityView):
    """Find DM recipients in the caller's current communities by display name."""

    def get(self, request: Request) -> Response:
        query = request.query_params.get("q", "").strip().casefold()
        if not 2 <= len(query) <= 100:
            raise serializers.ValidationError({"q": "Enter 2 to 100 characters."})
        active = GuestMembership.objects.filter(expires_at__gt=timezone.now())
        accounts = Membership.objects.annotate(
            display_name=Coalesce(
                NullIf(F("user__account__username"), Value("")), F("user__username")
            )
        ).filter(display_name__icontains=query)
        guests = active.select_related("community")
        if authenticated(request):
            groups = Membership.objects.filter(user=request.user).values("community_id")
            accounts = accounts.exclude(user=request.user)
        else:
            identity = guest_id(request)
            if not identity:
                return Response({"items": []})
            groups = active.filter(guest_id=identity).values("community_id")
            guests = guests.exclude(guest_id=identity)

        people = {}
        for member in (
            accounts.filter(community_id__in=groups)
            .order_by("id")
            .values("user_id", "community_id", "community__name", "display_name")
            .iterator()
        ):
            people.setdefault(
                ("account", member["user_id"]),
                {
                    "name": member["display_name"],
                    "community": member["community__name"],
                    "community_id": member["community_id"],
                    "target": {"user_id": str(member["user_id"])},
                },
            )
        for guest in guests.filter(community_id__in=groups).order_by("id").iterator():
            name = guest_name(guest.guest_id)
            if query in name.casefold():
                people.setdefault(
                    ("guest", guest.guest_id),
                    {
                        "name": name,
                        "community": guest.community.name,
                        "community_id": guest.community_id,
                        "target": {"guest_member_id": guest.pk},
                    },
                )
        items = sorted(people.values(), key=lambda item: item["name"].casefold())
        return Response({"items": items[:25]})


class PersonTarget(serializers.Serializer):
    user_id = serializers.CharField(max_length=64, required=False)
    guest_member_id = serializers.IntegerField(min_value=1, required=False)

    def validate(self, attrs):
        if len(attrs) != 1:
            raise serializers.ValidationError("Choose one community member.")
        return attrs


def shared_community(request: Request, community_id: int) -> Community:
    community = community_for(community_id)
    if role_for(community, viewer(request, community)) == "visitor":
        raise PermissionDenied("Join this community to use direct messages.")
    return community


def member_target(community: Community, target: dict) -> tuple[str, str]:
    if "guest_member_id" in target:
        guest = GuestMembership.objects.filter(
            pk=target["guest_member_id"], community=community, expires_at__gt=timezone.now()
        ).first()
        if guest is None:
            raise NotFound("Community member not found.")
        return f"g:{guest.guest_id}", guest_name(guest.guest_id)
    user_id = user_id_for(target["user_id"])
    if (
        community.owner_id != user_id
        and not Membership.objects.filter(community=community, user_id=user_id).exists()
    ):
        raise NotFound("Community member not found.")
    user = get_user_model().objects.get(pk=user_id)
    account = getattr(user, "account", None)
    return f"u:{user_id}", account.username if account and account.username else user.get_username()


class StartFromMember(CommunityView):
    def post(self, request: Request, community_id: int) -> Response:
        community = shared_community(request, community_id)
        parsed = PersonTarget(data=request.data)
        parsed.is_valid(raise_exception=True)
        key, name = member_target(community, parsed.validated_data)
        return start(request, key, name)


class GroupParticipantInput(serializers.Serializer):
    community_id = serializers.IntegerField(min_value=1)
    target = PersonTarget()


class GroupInput(serializers.Serializer):
    name = serializers.CharField(max_length=100, trim_whitespace=True)
    participants = GroupParticipantInput(many=True, min_length=2, max_length=19)


class DirectDetail(CommunityView):
    def get(self, request: Request, conversation_id: int) -> Response:
        conversation, key = conversation_for(request, conversation_id)
        pinned = ConversationPreference.objects.filter(
            conversation=conversation, actor=key, pinned=True, deleted=False
        ).exists()
        return Response(conversation_data(conversation, key, pinned=pinned))


class DirectConversations(CommunityView):
    def get(self, request: Request) -> Response:
        key = person_key(request)
        if key is None:
            return Response({"items": []})
        found = list(
            visible_conversations(key)
            .prefetch_related("participants")
            .annotate(
                is_pinned=Exists(
                    ConversationPreference.objects.filter(
                        conversation_id=OuterRef("pk"), actor=key, pinned=True, deleted=False
                    )
                )
            )
            .order_by("-is_pinned", "-updated_at", "-id")[:50]
        )
        counts = unread_counts(key, [item.pk for item in found])
        return Response(
            {
                "items": [
                    conversation_data(item, key, counts.get(item.pk, 0), item.is_pinned)
                    for item in found
                ]
            }
        )

    @transaction.atomic
    def post(self, request: Request) -> Response:
        key = person_key(request)
        if key is None:
            raise PermissionDenied("Join a community to create a private group.")
        parsed = GroupInput(data=request.data)
        parsed.is_valid(raise_exception=True)
        members = {key: author_name(request)}
        for participant in parsed.validated_data["participants"]:
            target, name = member_target(
                shared_community(request, participant["community_id"]), participant["target"]
            )
            if target in members:
                raise serializers.ValidationError("Choose distinct people other than yourself.")
            members[target] = name
        group = DirectConversation.objects.create(
            kind=DirectConversation.Kind.GROUP,
            name=parsed.validated_data["name"],
            pair_key=secrets.token_hex(32),
            first_key="",
            second_key="",
            first_name="",
            second_name="",
        )
        ConversationParticipant.objects.bulk_create(
            [
                ConversationParticipant(conversation=group, actor=actor, name=name)
                for actor, name in members.items()
            ]
        )
        return Response(conversation_data(group, key, 0), status=201)


class ConversationPreferenceInput(serializers.Serializer):
    pinned = serializers.BooleanField()


class DirectConversationPreference(CommunityView):
    def put(self, request: Request, conversation_id: int) -> Response:
        conversation, key = conversation_for(request, conversation_id)
        parsed = ConversationPreferenceInput(data=request.data)
        parsed.is_valid(raise_exception=True)
        preference, _ = ConversationPreference.objects.get_or_create(
            conversation=conversation, actor=key
        )
        preference.pinned = parsed.validated_data["pinned"]
        preference.save(update_fields=["pinned"])
        return Response({"pinned": preference.pinned})

    def delete(self, request: Request, conversation_id: int) -> Response:
        conversation, key = conversation_for(request, conversation_id)
        preference, _ = ConversationPreference.objects.get_or_create(
            conversation=conversation, actor=key
        )
        preference.deleted = True
        preference.save(update_fields=["deleted"])
        return Response(status=204)


class DirectMessages(CommunityView):
    def get(self, request: Request, conversation_id: int) -> Response:
        conversation, key = conversation_for(request, conversation_id)
        parsed = MessagePage(data=request.query_params)
        parsed.is_valid(raise_exception=True)
        data = parsed.validated_data
        query = DirectMessage.objects.filter(
            conversation=conversation, thread_root_id=data.get("thread")
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
                "items": [direct_message_data(item, key) for item in items],
                "has_more": len(found) > data["limit"],
            }
        )

    @transaction.atomic
    def post(self, request: Request, conversation_id: int) -> Response:
        conversation, key = conversation_for(request, conversation_id)
        DirectConversation.objects.select_for_update().only("pk").get(pk=conversation.pk)
        parsed = NewMessageInput(data=request.data)
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
            mentions=targets(parsed.validated_data["content"]),
            thread_root_id=thread_root(
                DirectMessage.objects.filter(conversation=conversation), parsed.validated_data
            ),
            **poll_fields(parsed.validated_data),
            **upload_fields(parsed.validated_data),
            author_name=author_name(request),
            content=parsed.validated_data["content"],
            reply_to_id=reply_id,
        )
        DirectConversation.objects.filter(pk=conversation.pk).update(updated_at=timezone.now())
        return Response(direct_message_data(message, key), status=201)


class DirectMessageDetail(CommunityView):
    def get(self, request: Request, conversation_id: int, message_id: int) -> Response:
        conversation, key = conversation_for(request, conversation_id)
        message = get_object_or_404(DirectMessage, conversation=conversation, pk=message_id)
        if "attachment" in request.query_params:
            return download(message)
        return Response(direct_message_data(message, key))

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
            message.pinned_at = None
            message.file_bytes = None
            message.file_name = ""
            message.save(
                update_fields=["content", "deleted_at", "pinned_at", "file_name", "file_bytes"]
            )
        return Response(status=204)


class DirectSearch(CommunityView):
    def get(self, request: Request, conversation_id: int) -> Response:
        conversation, key = conversation_for(request, conversation_id)
        found = search_messages(
            DirectMessage.objects.filter(conversation=conversation).prefetch_related("reactions"),
            request.query_params,
        )
        return Response({"items": [direct_message_data(item, key) for item in found]})


class DirectPin(CommunityView):
    def put(self, request: Request, conversation_id: int, message_id: int) -> Response:
        conversation, key = conversation_for(request, conversation_id)

        class Input(serializers.Serializer):
            pinned = serializers.BooleanField()

        parsed = Input(data=request.data)
        parsed.is_valid(raise_exception=True)
        messages = DirectMessage.objects.filter(
            conversation=conversation, pk=message_id, deleted_at__isnull=True
        )
        if not messages.update(
            pinned_at=timezone.now() if parsed.validated_data["pinned"] else None
        ):
            raise NotFound("Message unavailable.")
        return Response(direct_message_data(messages.get(), key))


class DirectPins(CommunityView):
    def get(self, request: Request, conversation_id: int) -> Response:
        conversation, key = conversation_for(request, conversation_id)
        messages = (
            DirectMessage.objects.filter(
                conversation=conversation, pinned_at__isnull=False, deleted_at__isnull=True
            )
            .order_by("-pinned_at")
            .prefetch_related("reactions")[:50]
        )
        return Response({"items": [direct_message_data(item, key) for item in messages]})


class DirectReactions(CommunityView):
    def put(self, request: Request, conversation_id: int, message_id: int) -> Response:
        conversation, key = conversation_for(request, conversation_id)
        message = get_object_or_404(
            DirectMessage, conversation=conversation, pk=message_id, deleted_at__isnull=True
        )

        class Input(ReactionInput):
            active = serializers.BooleanField()

        parsed = Input(data=request.data)
        parsed.is_valid(raise_exception=True)
        values = {"message": message, "actor": key, "emoji": parsed.validated_data["emoji"]}
        if parsed.validated_data["active"]:
            DirectReaction.objects.get_or_create(**values)
        else:
            DirectReaction.objects.filter(**values).delete()
        return Response(direct_message_data(message, key))
