"""App-wide heartbeat and community-scoped member presence."""

from datetime import timedelta

from django.utils import timezone
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from .dm_views import person_key
from .models import GuestMembership, Membership, Presence
from .permissions import role_for
from .views import CommunityView, community_for, viewer

ONLINE_WINDOW = timedelta(seconds=90)


class Heartbeat(CommunityView):
    def post(self, request):
        actor = person_key(request)
        if actor is not None:
            Presence.objects.update_or_create(actor=actor, defaults={"last_seen": timezone.now()})
        return Response(status=204)


class CommunityMembers(CommunityView):
    def get(self, request, community_id: int):
        community = community_for(community_id)
        if role_for(community, viewer(request, community)) == "visitor":
            raise PermissionDenied("Join this community to see member presence.")

        account_ids = set(
            Membership.objects.filter(community=community).values_list("user_id", flat=True)
        )
        if community.owner_id is not None:
            account_ids.add(community.owner_id)
        guest_rows = list(
            GuestMembership.objects.filter(
                community=community, expires_at__gt=timezone.now()
            ).values_list("id", "guest_id")
        )
        actors = [f"u:{identity}" for identity in account_ids] + [
            f"g:{identity}" for _, identity in guest_rows
        ]
        active_after = timezone.now() - ONLINE_WINDOW
        rows = {row.actor: row.last_seen for row in Presence.objects.filter(actor__in=actors)}
        accounts = {
            str(identity): self.status(rows.get(f"u:{identity}"), active_after)
            for identity in account_ids
        }
        guests = {
            str(member_id): self.status(rows.get(f"g:{identity}"), active_after)
            for member_id, identity in guest_rows
        }
        return Response({"accounts": accounts, "guests": guests})

    @staticmethod
    def status(last_seen, active_after):
        if last_seen is None:
            return {"online": False, "last_seen": None}
        return {
            "online": last_seen >= active_after,
            "last_seen": last_seen,
        }
