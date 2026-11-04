"""Store mention targets at send time. Actor keys never enter the public payload."""

import re
from datetime import timedelta

from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from .models import RoomMemberState

TOKEN = re.compile(r"(?<!\w)@(?:\[([^\]\n]{1,150})\]|([\w.-]{1,150}))")
ROLES = {"owner", "moderator", "member", "everyone", "here"}


def targets(content, *, channel=None, role=None):
    targets = set()
    for named, simple in TOKEN.findall(content):
        name = (named or simple).casefold()
        if channel and not named and name in ROLES:
            if role not in {"owner", "moderator"}:
                raise PermissionDenied("Only moderators and owners can mention a whole group.")
            if name == "here":
                targets.update(
                    RoomMemberState.objects.filter(
                        channel=channel, last_active__gte=timezone.now() - timedelta(seconds=65)
                    ).values_list("actor", flat=True)
                )
            else:
                targets.add("role:" + name)
        else:
            targets.add("name:" + name)
    return sorted(targets)
