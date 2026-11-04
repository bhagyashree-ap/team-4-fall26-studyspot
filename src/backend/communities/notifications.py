"""Unread activity is evaluated against current access and each room's read cursor."""

from django.db.models import F, OuterRef, Q, Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework.response import Response

from .dm_views import person_key
from .message_views import authenticated, author_name
from .models import DirectMessage, GuestMembership, Membership, Message, RoomMemberState
from .views import CommunityView, guest_id


def unread(messages, key, room_field, mentioned):
    state = RoomMemberState.objects.filter(actor=key, **{room_field: OuterRef(room_field)})
    return (
        messages.annotate(
            cursor=Coalesce(state.values("last_read")[:1], Value(0)),
            mode=Coalesce(state.values("alerts")[:1], Value("all")),
        )
        .filter(pk__gt=F("cursor"), deleted_at__isnull=True)
        .filter(Q(mode="all") | (Q(mode="mentions") & mentioned))
        .order_by("-created_at", "-pk")
    )


class Notifications(CommunityView):
    def get(self, request):
        key = person_key(request)
        if key is None:
            return Response({"items": []})
        community = "channel__community_id"
        if authenticated(request):
            memberships = Membership.objects.filter(user=request.user)
            owner = Q(channel__community__owner=request.user)
            mod = (
                Q(
                    **{
                        community + "__in": memberships.filter(role="moderator").values(
                            "community_id"
                        )
                    }
                )
                & ~owner
            )
            member = Q(**{community + "__in": memberships.values("community_id")}) & ~(owner | mod)
            own_messages = Q(author=request.user)
        else:
            memberships = GuestMembership.objects.filter(
                guest_id=guest_id(request), expires_at__gt=timezone.now()
            )
            joined = Q(**{community + "__in": memberships.values("community_id")})
            owner = joined & Q(
                channel__community__owner__isnull=True,
                channel__community_id__in=request.session.get("guest_communities", []),
            )
            mod = Q(pk__in=[])
            member = joined & ~owner
            own_messages = Q(guest_id=guest_id(request))
        direct_mention = Q(mentions__overlap=[key, "name:" + author_name(request).casefold()])
        mentioned = direct_mention | Q(mentions__contains=["role:everyone"])
        for role, condition in [("member", member), ("owner", owner), ("moderator", mod)]:
            mentioned |= condition & Q(mentions__contains=["role:" + role])
        channels = Message.objects.filter(
            owner | mod | (member & Q(channel__private=False))
        ).exclude(own_messages)
        channel_rows = list(
            unread(channels, key, "channel_id", mentioned).values(
                "id",
                "content",
                "author_name",
                "created_at",
                "channel_id",
                "channel__community_id",
                "channel__name",
                "channel__community__name",
            )[:30]
        )
        private = DirectMessage.objects.filter(
            Q(conversation__first_key=key) | Q(conversation__second_key=key)
        ).exclude(sender_key=key)
        dm_rows = list(
            unread(private, key, "conversation_id", direct_mention).values(
                "id", "content", "author_name", "created_at", "conversation_id"
            )[:30]
        )
        items = sorted(channel_rows + dm_rows, key=lambda row: row["created_at"], reverse=True)
        return Response({"items": items[:30]})
