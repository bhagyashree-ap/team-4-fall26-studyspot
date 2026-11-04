"""Interactions shared by channel members and direct conversation participants."""

from datetime import timedelta

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from .dm_views import conversation_for, direct_message_data, person_key
from .message_views import author_name, channel_for, member_role, message_data, poll_data
from .models import DirectMessage, RoomMemberState, Vote
from .views import CommunityView


def room_messages(request, *, community_id=None, channel_id=None, conversation_id=None):
    if conversation_id is not None:
        conversation, key = conversation_for(request, conversation_id)
        return DirectMessage.objects.filter(conversation=conversation), key
    if community_id is None or channel_id is None:
        raise ValueError("A channel route requires both community and channel IDs.")
    channel = channel_for(community_id, channel_id)
    member_role(request, channel)
    return channel.messages.all(), person_key(request)


class PollVote(CommunityView):
    def put(self, request, message_id, **room):
        messages, key = room_messages(request, **room)
        message = get_object_or_404(messages, pk=message_id, deleted_at__isnull=True)
        if not message.poll_id:
            raise NotFound("Poll unavailable.")

        class Ballot(serializers.Serializer):
            choice = serializers.IntegerField(min_value=0, max_value=len(message.poll.options) - 1)

        parsed = Ballot(data=request.data)
        parsed.is_valid(raise_exception=True)
        Vote.objects.update_or_create(poll=message.poll, actor=key, defaults=parsed.validated_data)
        return Response(poll_data(messages.get(pk=message_id), key))


def room_state(room):
    if "conversation_id" in room:
        return RoomMemberState.objects.filter(conversation_id=room["conversation_id"])
    return RoomMemberState.objects.filter(channel_id=room["channel_id"])


def state_scope(room):
    return {k: v for k, v in room.items() if k != "community_id"}


class ReadMarker(CommunityView):
    def put(self, request, **room):
        messages, key = room_messages(request, **room)

        class Marker(serializers.Serializer):
            unread_from = serializers.IntegerField(min_value=1, required=False)

        parsed = Marker(data=request.data)
        parsed.is_valid(raise_exception=True)
        target = parsed.validated_data.get("unread_from")
        if target:
            get_object_or_404(messages, pk=target)
            last_read = target - 1
        else:
            last_read = messages.order_by("-pk").values_list("pk", flat=True).first() or 0
        RoomMemberState.objects.update_or_create(
            actor=key,
            **state_scope(room),
            defaults={"last_read": last_read, "name": author_name(request)},
        )
        return Response({"last_read": last_read})


class RoomPresence(CommunityView):
    def get(self, request, **room):
        _, key = room_messages(request, **room)
        names = (
            room_state(room)
            .exclude(actor=key)
            .filter(typing_until__gt=timezone.now())
            .order_by("-typing_until")
            .values_list("name", flat=True)[:5]
        )
        last_read = (
            room_state(room).filter(actor=key).values_list("last_read", flat=True).first() or 0
        )
        mode = room_state(room).filter(actor=key).values_list("alerts", flat=True).first() or "all"
        return Response({"typing": list(names), "last_read": last_read, "alerts": mode})

    def post(self, request, **room):
        _, key = room_messages(request, **room)

        class Signal(serializers.Serializer):
            typing = serializers.BooleanField(required=False)

        parsed = Signal(data=request.data)
        parsed.is_valid(raise_exception=True)
        defaults = {"name": author_name(request), "last_active": timezone.now()}
        if "typing" in parsed.validated_data:
            defaults["typing_until"] = (
                timezone.now() + timedelta(seconds=7) if parsed.validated_data["typing"] else None
            )
        scope = {k: v for k, v in room.items() if k != "community_id"}
        RoomMemberState.objects.update_or_create(actor=key, **scope, defaults=defaults)
        return Response(status=204)


class AlertPreference(CommunityView):
    def put(self, request, **room):
        _, key = room_messages(request, **room)

        class Preference(serializers.Serializer):
            alerts = serializers.ChoiceField(choices=RoomMemberState.Alerts.choices)

        parsed = Preference(data=request.data)
        parsed.is_valid(raise_exception=True)
        RoomMemberState.objects.update_or_create(
            actor=key,
            **state_scope(room),
            defaults={"name": author_name(request), **parsed.validated_data},
        )
        return Response(parsed.validated_data)


class MessageSnapshot(CommunityView):
    def post(self, request, **room):
        class Window(serializers.Serializer):
            ids = serializers.ListField(child=serializers.IntegerField(min_value=1), max_length=250)

        parsed = Window(data=request.data)
        parsed.is_valid(raise_exception=True)
        messages, key = room_messages(request, **room)
        window = messages.filter(pk__in=parsed.validated_data["ids"]).prefetch_related("reactions")
        if "conversation_id" in room:
            return Response({"items": [direct_message_data(m, key) for m in window]})
        channel = channel_for(room["community_id"], room["channel_id"])
        role = member_role(request, channel)
        return Response({"items": [message_data(request, m, role) for m in window]})
