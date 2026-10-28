"""Public discovery and session-backed community management."""

import hashlib
import secrets
from datetime import datetime

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Count, Q
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import NotAuthenticated, NotFound, PermissionDenied
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.authentication import Auth0Authentication

from . import services
from .models import Ban, Channel, Community, GuestMembership, Invite, Membership, ModerationEvent
from .permissions import Action, GuestMember, GuestOwner, require, role_for
from .serializers import (
    ChannelSerializer,
    ChannelWriteSerializer,
    CommunitySerializer,
    CommunityWriteSerializer,
    InviteWriteSerializer,
    MemberSerializer,
    RoleWriteSerializer,
)


class CommunitySessionAuthentication(SessionAuthentication):
    def authenticate(self, request: Request):
        if request.method not in {"GET", "HEAD", "OPTIONS"} and not getattr(
            request._request.user, "is_authenticated", False
        ):
            self.enforce_csrf(request)
        return super().authenticate(request)

    def authenticate_header(self, request: Request) -> str:
        return "Session"


class CommunityView(APIView):
    authentication_classes = [Auth0Authentication, CommunitySessionAuthentication]


def actor(request: Request):
    if not request.user or not request.user.is_authenticated or not request.user.is_active:
        raise NotAuthenticated("Sign in with an active account to continue.")
    return request.user


def guest_id(request: Request) -> str | None:
    return request.session.get("community_guest_id")


def ensure_guest_id(request: Request) -> str:
    value = guest_id(request)
    if value is None:
        value = secrets.token_hex(16)
        request.session["community_guest_id"] = value
    return value


def guest_expiry(request: Request) -> datetime:
    request.session.set_expiry(request.session.get_session_cookie_age())
    return request.session.get_expiry_date()


def counted_communities():
    return Community.objects.annotate(
        member_count=Count("memberships", distinct=True)
        + Count(
            "guest_memberships",
            filter=Q(guest_memberships__expires_at__gt=timezone.now()),
            distinct=True,
        )
    )


def viewer(request: Request, community: Community):
    if community.owner_id is None and community.pk in request.session.get("guest_communities", []):
        return GuestOwner(community.pk)
    if not getattr(request.user, "is_authenticated", False):
        identity = guest_id(request)
        if (
            identity
            and GuestMembership.objects.filter(
                community=community, guest_id=identity, expires_at__gt=timezone.now()
            ).exists()
        ):
            return GuestMember(community.pk)
    return request.user


def principal(request: Request, community: Community):
    user = viewer(request, community)
    return user if isinstance(user, GuestOwner) else actor(request)


def community_for(community_id: int) -> Community:
    return get_object_or_404(Community, pk=community_id)


def user_id_for(raw: str):
    """Parse the account model's primary key before applying a filter."""
    try:
        return get_user_model()._meta.pk.to_python(raw)
    except (DjangoValidationError, ValueError, TypeError) as exc:
        raise NotFound("User not found.") from exc


def summary(community: Community, user: object, role: str | None = None) -> dict:
    data = CommunitySerializer(community).data
    data["role"] = role if role is not None else role_for(community, user)
    return data


def page(request: Request) -> tuple[int, int]:
    class Page(serializers.Serializer):
        limit = serializers.IntegerField(default=20, min_value=1, max_value=50)
        offset = serializers.IntegerField(default=0, min_value=0)

    parsed = Page(data=request.query_params)
    parsed.is_valid(raise_exception=True)
    return parsed.validated_data["limit"], parsed.validated_data["offset"]


class CommunityList(CommunityView):
    def get(self, request: Request) -> Response:
        actor(request)
        get_token(request._request)
        limit, offset = page(request)
        query = request.query_params.get("q", "").strip()
        if len(query) > 100:
            raise serializers.ValidationError({"q": "Search must be at most 100 characters."})
        mine = request.query_params.get("mine")
        if mine not in {None, "true", "false"}:
            raise serializers.ValidationError({"mine": "Use true or false."})
        communities = counted_communities()
        if query:
            communities = communities.filter(
                Q(name__icontains=query) | Q(school__icontains=query) | Q(course__icontains=query)
            )
        guest_ids = request.session.get("guest_communities", [])
        identity = guest_id(request)
        if mine == "true":
            owned_or_joined = Q(pk__in=guest_ids, owner__isnull=True)
            if identity:
                owned_or_joined |= Q(
                    pk__in=GuestMembership.objects.filter(
                        guest_id=identity, expires_at__gt=timezone.now()
                    ).values("community_id")
                )
            if getattr(request.user, "is_authenticated", False):
                owned_or_joined |= Q(
                    pk__in=Membership.objects.filter(user=request.user).values("community_id")
                )
            communities = communities.filter(owned_or_joined)
        found = list(communities[offset : offset + limit + 1])
        roles = {}
        if request.user and request.user.is_authenticated:
            roles = dict(
                Membership.objects.filter(
                    user=request.user, community__in=found[:limit]
                ).values_list("community_id", "role")
            )
        guest_roles = set()
        if identity and not getattr(request.user, "is_authenticated", False):
            guest_roles = set(
                GuestMembership.objects.filter(
                    guest_id=identity,
                    community__in=found[:limit],
                    expires_at__gt=timezone.now(),
                ).values_list("community_id", flat=True)
            )
        return Response(
            {
                "items": [
                    summary(
                        item,
                        request.user,
                        "owner"
                        if (
                            item.owner_id is not None
                            and item.owner_id == getattr(request.user, "pk", None)
                        )
                        or (item.owner_id is None and item.pk in guest_ids)
                        else roles.get(item.pk, "member" if item.pk in guest_roles else "visitor"),
                    )
                    for item in found[:limit]
                ],
                "has_more": len(found) > limit,
            }
        )

    def post(self, request: Request) -> Response:
        user = actor(request)
        parsed = CommunityWriteSerializer(data=request.data)
        parsed.is_valid(raise_exception=True)
        created = services.create_community(user, parsed.validated_data)
        created.member_count = 1
        return Response(summary(created, viewer(request, created)), status=201)


class CommunityDetail(CommunityView):
    def get(self, request: Request, community_id: int) -> Response:
        community = get_object_or_404(counted_communities(), pk=community_id)
        return Response(
            {
                **summary(community, viewer(request, community)),
                "channels": ChannelSerializer(community.channels.all(), many=True).data,
            }
        )

    def patch(self, request: Request, community_id: int) -> Response:
        parsed = CommunityWriteSerializer(data=request.data, partial=True)
        parsed.is_valid(raise_exception=True)
        with transaction.atomic():
            community = get_object_or_404(Community.objects.select_for_update(), pk=community_id)
            user = principal(request, community)
            require(community, user, Action.MANAGE)
            for field, value in parsed.validated_data.items():
                setattr(community, field, value)
            if parsed.validated_data:
                community.save(update_fields=list(parsed.validated_data))
        community.member_count = services.member_count(community)
        return Response(summary(community, user))

    def delete(self, request: Request, community_id: int) -> Response:
        with transaction.atomic():
            community = get_object_or_404(Community.objects.select_for_update(), pk=community_id)
            user = principal(request, community)
            require(community, user, Action.DELETE)
            community.delete()
        return Response(status=204)


class Join(CommunityView):
    def post(self, request: Request, community_id: int) -> Response:
        community = community_for(community_id)
        if getattr(request.user, "is_authenticated", False):
            services.join(community, actor(request), guest_id(request))
        else:
            identity = ensure_guest_id(request)
            services.join_guest(community, identity, guest_expiry(request))
        return Response({"joined": True})


class Leave(CommunityView):
    def post(self, request: Request, community_id: int) -> Response:
        community = community_for(community_id)
        if getattr(request.user, "is_authenticated", False):
            services.leave(community, actor(request))
        else:
            if community.owner_id is None and community.pk in request.session.get(
                "guest_communities", []
            ):
                raise PermissionDenied("Transfer ownership or delete the community before leaving.")
            identity = guest_id(request)
            if identity:
                services.leave_guest(community, identity)
        return Response({"joined": False})


class Members(CommunityView):
    def get(self, request: Request, community_id: int) -> Response:
        community = community_for(community_id)
        limit, offset = page(request)
        found_accounts = list(
            Membership.objects.filter(community=community)
            .select_related("user__account")
            .order_by("id")[offset : offset + limit + 1]
        )
        found_guests = list(
            GuestMembership.objects.filter(
                community=community, expires_at__gt=timezone.now()
            ).order_by("joined_at", "id")[offset : offset + limit + 1]
        )
        current_guest = guest_id(request)
        owns_as_guest = community_id in request.session.get("guest_communities", [])
        return Response(
            {
                "items": MemberSerializer(
                    found_accounts[:limit], many=True, context={"request": request}
                ).data,
                "has_more": len(found_accounts) > limit,
                "guest_items": [
                    {
                        "id": guest.pk,
                        "display_name": f"Guest {hashlib.sha256(guest.guest_id.encode()).hexdigest()[:6]}",
                        "role": "owner"
                        if owns_as_guest and guest.guest_id == current_guest
                        else "member",
                        "is_me": guest.guest_id == current_guest,
                    }
                    for guest in found_guests[:limit]
                ],
                "guest_has_more": len(found_guests) > limit,
                "guest_count": GuestMembership.objects.filter(
                    community=community, expires_at__gt=timezone.now()
                ).count(),
            }
        )


class MemberDetail(CommunityView):
    def patch(self, request: Request, community_id: int, user_id: str) -> Response:
        parsed = RoleWriteSerializer(data=request.data)
        parsed.is_valid(raise_exception=True)
        community = community_for(community_id)
        services.set_role(
            community,
            principal(request, community),
            user_id_for(user_id),
            parsed.validated_data["role"],
        )
        return Response({"role": parsed.validated_data["role"]})

    def delete(self, request: Request, community_id: int, user_id: str) -> Response:
        community = community_for(community_id)
        services.moderate(community, principal(request, community), user_id_for(user_id), "kick")
        return Response(status=204)


class Transfer(CommunityView):
    def post(self, request: Request, community_id: int) -> Response:
        class Target(serializers.Serializer):
            user_id = serializers.CharField(max_length=64)

        parsed = Target(data=request.data)
        parsed.is_valid(raise_exception=True)
        community = community_for(community_id)
        services.transfer(
            community,
            principal(request, community),
            user_id_for(parsed.validated_data["user_id"]),
        )
        return Response({"owner_id": parsed.validated_data["user_id"]})


class Channels(CommunityView):
    def get(self, request: Request, community_id: int) -> Response:
        community = community_for(community_id)
        return Response(ChannelSerializer(community.channels.all(), many=True).data)

    def post(self, request: Request, community_id: int) -> Response:
        parsed = ChannelWriteSerializer(data=request.data)
        parsed.is_valid(raise_exception=True)
        community = community_for(community_id)
        channel = services.create_channel(
            community, principal(request, community), parsed.validated_data["name"]
        )
        return Response(ChannelSerializer(channel).data, status=201)


class ChannelDetail(CommunityView):
    def delete(self, request: Request, community_id: int, channel_id: int) -> Response:
        with transaction.atomic():
            community = get_object_or_404(Community.objects.select_for_update(), pk=community_id)
            require(community, principal(request, community), Action.MANAGE)
            get_object_or_404(Channel, pk=channel_id, community=community).delete()
            remaining = list(Channel.objects.filter(community=community).order_by("position", "id"))
            for index, channel in enumerate(remaining):
                channel.position = index
            Channel.objects.bulk_update(remaining, ["position"])
        return Response(status=204)

    def patch(self, request: Request, community_id: int, channel_id: int) -> Response:
        class Update(serializers.Serializer):
            name = serializers.RegexField(r"^[a-z0-9][a-z0-9-]{0,49}$", required=False)
            position = serializers.IntegerField(min_value=0, max_value=19, required=False)
            archived = serializers.BooleanField(required=False)

        parsed = Update(data=request.data)
        parsed.is_valid(raise_exception=True)
        with transaction.atomic():
            community = get_object_or_404(Community.objects.select_for_update(), pk=community_id)
            user = principal(request, community)
            require(community, user, Action.MANAGE)
            channel = get_object_or_404(Channel, pk=channel_id, community=community)
            name = parsed.validated_data.get("name")
            if (
                name
                and Channel.objects.filter(community=community, name__iexact=name)
                .exclude(pk=channel.pk)
                .exists()
            ):
                raise serializers.ValidationError("A channel with this name already exists.")
            position = parsed.validated_data.pop("position", None)
            if position is not None:
                ordered = list(
                    Channel.objects.filter(community=community).order_by("position", "id")
                )
                ordered.remove(channel)
                ordered.insert(min(position, len(ordered)), channel)
                for index, item in enumerate(ordered):
                    item.position = index
                Channel.objects.bulk_update(ordered, ["position"])
            for field, value in parsed.validated_data.items():
                setattr(channel, field, value)
            if parsed.validated_data:
                channel.save(update_fields=list(parsed.validated_data))
        return Response(ChannelSerializer(channel).data)


class Invites(CommunityView):
    def get(self, request: Request, community_id: int) -> Response:
        community = community_for(community_id)
        require(community, principal(request, community), Action.INVITE)
        return Response(
            list(
                Invite.objects.filter(community=community)
                .values("id", "created_at", "expires_at", "max_uses", "uses", "revoked")
                .order_by("-id")[:50]
            )
        )

    def post(self, request: Request, community_id: int) -> Response:
        parsed = InviteWriteSerializer(data=request.data)
        parsed.is_valid(raise_exception=True)
        community = community_for(community_id)
        invite, token = services.create_invite(
            community, principal(request, community), parsed.validated_data
        )
        return Response(
            {
                "id": invite.id,
                "token": token,
                "expires_at": invite.expires_at,
                "max_uses": invite.max_uses,
            },
            status=201,
        )


class InviteDetail(CommunityView):
    def delete(self, request: Request, community_id: int, invite_id: int) -> Response:
        with transaction.atomic():
            community = get_object_or_404(Community.objects.select_for_update(), pk=community_id)
            require(community, principal(request, community), Action.INVITE)
            invite = get_object_or_404(Invite, pk=invite_id, community=community)
            invite.revoked = True
            invite.save(update_fields=["revoked"])
        return Response(status=204)


class Redeem(CommunityView):
    def post(self, request: Request, token: str) -> Response:
        if getattr(request.user, "is_authenticated", False):
            community = services.redeem(token, actor(request))
        else:
            community = services.redeem(
                token,
                guest_id=ensure_guest_id(request),
                expires_at=guest_expiry(request),
            )
        return Response({"community_id": community.pk})


class Moderation(CommunityView):
    def get(self, request: Request, community_id: int) -> Response:
        community = community_for(community_id)
        require(community, principal(request, community), Action.MODERATE)
        return Response(
            {
                "events": list(
                    ModerationEvent.objects.filter(community=community).values(
                        "id", "actor_id", "target_id", "action", "created_at"
                    )[:50]
                ),
                "banned_user_ids": list(
                    Ban.objects.filter(community=community).values_list("user_id", flat=True)[:50]
                ),
            }
        )

    def post(self, request: Request, community_id: int) -> Response:
        class Decision(serializers.Serializer):
            user_id = serializers.CharField(max_length=64)
            action = serializers.ChoiceField(choices=["ban", "unban", "kick"])

        parsed = Decision(data=request.data)
        parsed.is_valid(raise_exception=True)
        target_id = user_id_for(parsed.validated_data["user_id"])
        if not get_user_model().objects.filter(pk=target_id).exists():
            raise NotFound("User not found.")
        community = community_for(community_id)
        services.moderate(
            community, principal(request, community), target_id, parsed.validated_data["action"]
        )
        return Response({"action": parsed.validated_data["action"]})


class AdminCommunity(CommunityView):
    """A separate platform action, never an implicit community owner grant."""

    def delete(self, request: Request, community_id: int) -> Response:
        user = actor(request)
        if not user.is_staff:
            raise PermissionDenied("A StudySpot admin account is required.")
        with transaction.atomic():
            community = get_object_or_404(Community.objects.select_for_update(), pk=community_id)
            community.delete()
        return Response(status=204)
