"""Small transactional operations whose invariants span several rows."""

import hashlib
import secrets
from datetime import datetime, timedelta

from django.contrib.auth import get_user_model
from django.db import models, transaction
from django.db.models import F
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from .models import Ban, Channel, Community, GuestMembership, Invite, Membership, ModerationEvent
from .permissions import Action, GuestOwner, require, role_for

MAX_OWNED = 5
MAX_JOINED = 100
MAX_MEMBERS = 1000
MAX_CHANNELS = 20
MAX_INVITES = 10


def member_count(community: Community) -> int:
    return (
        Membership.objects.filter(community=community).count()
        + GuestMembership.objects.filter(community=community, expires_at__gt=timezone.now()).count()
    )


def _lock_user(user_id: object) -> None:
    get_user_model().objects.select_for_update().get(pk=user_id)


def _join(community: Community, user: object) -> Membership:
    if Ban.objects.filter(community=community, user=user).exists():
        raise PermissionDenied("You are banned from this community.")
    existing = Membership.objects.filter(community=community, user=user).first()
    if existing:
        return existing
    if Membership.objects.filter(user=user).count() >= MAX_JOINED:
        raise ValidationError("You have joined the maximum number of communities.")
    if member_count(community) >= MAX_MEMBERS:
        raise ValidationError("This community has the maximum number of members.")
    return Membership.objects.create(community=community, user=user)


@transaction.atomic
def create_community(user: object, data: dict) -> Community:
    _lock_user(user.pk)
    if Community.objects.filter(owner=user).count() >= MAX_OWNED:
        raise ValidationError("You own the maximum number of communities.")
    if Membership.objects.filter(user=user).count() >= MAX_JOINED:
        raise ValidationError("You have joined the maximum number of communities.")
    community = Community.objects.create(owner=user, **data)
    Membership.objects.create(community=community, user=user)
    Channel.objects.create(community=community, name="general")
    return community


@transaction.atomic
def create_guest_community(data: dict, guest_id: str, expires_at: datetime) -> Community:
    community = Community.objects.create(**data)
    GuestMembership.objects.create(community=community, guest_id=guest_id, expires_at=expires_at)
    Channel.objects.create(community=community, name="general")
    return community


@transaction.atomic
def join(community: Community, user: object, guest_id: str | None = None) -> Membership:
    community = Community.objects.select_for_update().get(pk=community.pk)
    if role_for(community, user) == "visitor":
        require(community, user, Action.JOIN)
    _lock_user(user.pk)
    if guest_id:
        GuestMembership.objects.filter(community=community, guest_id=guest_id).delete()
    return _join(community, user)


@transaction.atomic
def join_guest(community: Community, guest_id: str, expires_at: datetime) -> None:
    community = Community.objects.select_for_update().get(pk=community.pk)
    existing = GuestMembership.objects.filter(community=community, guest_id=guest_id).first()
    if existing:
        existing.expires_at = expires_at
        existing.save(update_fields=["expires_at"])
        return
    if (
        GuestMembership.objects.filter(guest_id=guest_id, expires_at__gt=timezone.now()).count()
        >= MAX_JOINED
    ):
        raise ValidationError("You have joined the maximum number of communities.")
    if member_count(community) >= MAX_MEMBERS:
        raise ValidationError("This community has the maximum number of members.")
    GuestMembership.objects.create(community=community, guest_id=guest_id, expires_at=expires_at)


@transaction.atomic
def leave_guest(community: Community, guest_id: str) -> None:
    community = Community.objects.select_for_update().get(pk=community.pk)
    GuestMembership.objects.filter(community=community, guest_id=guest_id).delete()


@transaction.atomic
def leave(community: Community, user: object) -> None:
    community = Community.objects.select_for_update().get(pk=community.pk)
    require(community, user, Action.LEAVE)
    if community.owner_id == user.pk:
        raise PermissionDenied("Transfer ownership before leaving.")
    Membership.objects.filter(community=community, user=user).delete()


@transaction.atomic
def create_channel(community: Community, user: object, name: str) -> Channel:
    community = Community.objects.select_for_update().get(pk=community.pk)
    require(community, user, Action.MANAGE)
    if Channel.objects.filter(community=community).count() >= MAX_CHANNELS:
        raise ValidationError("This community has the maximum number of channels.")
    if Channel.objects.filter(community=community, name__iexact=name).exists():
        raise ValidationError("A channel with this name already exists.")
    return Channel.objects.create(
        community=community, name=name, position=community.channels.count()
    )


@transaction.atomic
def create_invite(community: Community, user: object, data: dict) -> tuple[Invite, str]:
    community = Community.objects.select_for_update().get(pk=community.pk)
    require(community, user, Action.INVITE)
    if (
        Invite.objects.filter(community=community, revoked=False)
        .filter(models.Q(expires_at__isnull=True) | models.Q(expires_at__gt=timezone.now()))
        .filter(models.Q(max_uses__isnull=True) | models.Q(uses__lt=F("max_uses")))
        .count()
        >= MAX_INVITES
    ):
        raise ValidationError("This community has the maximum number of active invites.")
    token = secrets.token_urlsafe(32)
    hours = data.get("expires_in_hours")
    invite = Invite.objects.create(
        community=community,
        created_by=None if isinstance(user, GuestOwner) else user,
        token_hash=hashlib.sha256(token.encode()).hexdigest(),
        expires_at=timezone.now() + timedelta(hours=hours) if hours else None,
        max_uses=data.get("max_uses"),
    )
    return invite, token


@transaction.atomic
def redeem(
    token: str,
    user: object | None = None,
    guest_id: str | None = None,
    expires_at: datetime | None = None,
) -> Community:
    digest = hashlib.sha256(token.encode()).hexdigest()
    community_id = (
        Invite.objects.filter(token_hash=digest).values_list("community_id", flat=True).first()
    )
    if community_id is None:
        raise NotFound("Invite not found or expired.")
    Community.objects.select_for_update().get(pk=community_id)
    invite = Invite.objects.select_for_update().select_related("community").get(token_hash=digest)
    if (
        invite is None
        or invite.revoked
        or (invite.expires_at and invite.expires_at <= timezone.now())
    ):
        raise NotFound("Invite not found or expired.")
    if invite.max_uses is not None and invite.uses >= invite.max_uses:
        raise NotFound("Invite has reached its use limit.")
    if user is None:
        if guest_id is None or expires_at is None:
            raise ValueError("Guest identity and expiry are required.")
        was_member = GuestMembership.objects.filter(
            community=invite.community, guest_id=guest_id, expires_at__gt=timezone.now()
        ).exists()
        join_guest(invite.community, guest_id, expires_at)
    else:
        if role_for(invite.community, user) == "visitor":
            require(invite.community, user, Action.JOIN)
        _lock_user(user.pk)
        was_member = Membership.objects.filter(community=invite.community, user=user).exists()
        _join(invite.community, user)
    if not was_member:
        invite.uses += 1
        invite.save(update_fields=["uses"])
    return invite.community


@transaction.atomic
def set_role(community: Community, actor: object, target_id: object, role: str) -> None:
    community = Community.objects.select_for_update().get(pk=community.pk)
    require(community, actor, Action.SET_MODERATOR)
    if target_id == community.owner_id:
        raise ValidationError("The owner role cannot be changed here.")
    member = Membership.objects.filter(community=community, user_id=target_id).first()
    if member is None:
        raise NotFound("Member not found.")
    member.role = role
    member.save(update_fields=["role"])
    ModerationEvent.objects.create(
        community=community,
        actor=None if isinstance(actor, GuestOwner) else actor,
        target_id=target_id,
        action=f"role:{role}",
    )


@transaction.atomic
def moderate(community: Community, actor: object, target_id: object, action: str) -> None:
    community = Community.objects.select_for_update().get(pk=community.pk)
    require(community, actor, Action.MODERATE)
    if target_id == community.owner_id:
        raise PermissionDenied("The owner cannot be moderated.")
    member = Membership.objects.filter(community=community, user_id=target_id).first()
    if (
        member
        and member.role == Membership.Role.MODERATOR
        and role_for(community, actor) != "owner"
    ):
        raise PermissionDenied("Only the owner can moderate a moderator.")
    if action == "unban":
        Ban.objects.filter(community=community, user_id=target_id).delete()
    elif action in {"kick", "ban"}:
        if action == "ban":
            Ban.objects.get_or_create(community=community, user_id=target_id)
        if member:
            member.delete()
    else:
        raise ValidationError("Unknown moderation action.")
    ModerationEvent.objects.create(
        community=community,
        actor=None if isinstance(actor, GuestOwner) else actor,
        target_id=target_id,
        action=action,
    )


@transaction.atomic
def transfer(community: Community, actor: object, target_id: object) -> None:
    community = Community.objects.select_for_update().get(pk=community.pk)
    require(community, actor, Action.TRANSFER)
    member = Membership.objects.filter(community=community, user_id=target_id).first()
    if member is None:
        raise NotFound("New owner must be a member.")
    if community.owner_id == target_id:
        return
    _lock_user(target_id)
    if Community.objects.filter(owner_id=target_id).count() >= MAX_OWNED:
        raise ValidationError("This member already owns the maximum number of communities.")
    community.owner_id = target_id
    community.save(update_fields=["owner"])
    member.role = Membership.Role.MEMBER
    member.save(update_fields=["role"])
    ModerationEvent.objects.create(
        community=community,
        actor=None if isinstance(actor, GuestOwner) else actor,
        target_id=target_id,
        action="transfer",
    )
