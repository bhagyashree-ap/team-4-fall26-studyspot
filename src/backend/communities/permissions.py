"""One permission policy for community operations."""

from dataclasses import dataclass
from enum import StrEnum

from rest_framework.exceptions import PermissionDenied

from .models import Community, Membership


class Action(StrEnum):
    JOIN = "join"
    LEAVE = "leave"
    INVITE = "invite"
    MODERATE = "moderate"
    SET_MODERATOR = "set_moderator"
    MANAGE = "manage"
    TRANSFER = "transfer"
    DELETE = "delete"


ROLE_ACTIONS = {
    "visitor": {Action.JOIN},
    "member": {Action.LEAVE},
    "moderator": {Action.LEAVE, Action.INVITE, Action.MODERATE},
    "owner": set(Action),
}


@dataclass(frozen=True)
class GuestOwner:
    community_id: int
    pk: None = None
    is_authenticated: bool = True
    is_active: bool = True


@dataclass(frozen=True)
class GuestMember:
    community_id: int
    pk: None = None
    is_authenticated: bool = True
    is_active: bool = True


def role_for(community: Community, user: object) -> str:
    """Resolve ownership before membership; the owner field is authoritative."""
    if isinstance(user, GuestOwner):
        return (
            "owner"
            if community.owner_id is None and community.pk == user.community_id
            else "visitor"
        )
    if isinstance(user, GuestMember):
        return "member" if community.pk == user.community_id else "visitor"
    if not getattr(user, "is_authenticated", False):
        return "visitor"
    if community.owner_id == user.pk:
        return "owner"
    return (
        Membership.objects.filter(community=community, user=user)
        .values_list("role", flat=True)
        .first()
        or "visitor"
    )


def require(community: Community, user: object, action: Action) -> str:
    """Deny absent grants and suspended users; admins use explicit staff endpoints."""
    if not getattr(user, "is_authenticated", False) or not getattr(user, "is_active", False):
        raise PermissionDenied("An active account is required.")
    role = role_for(community, user)
    if action not in ROLE_ACTIONS[role]:
        raise PermissionDenied("You cannot perform this action in this community.")
    return role
