"""The sample seed is repeatable and its DMs reach the active local guest."""

import pytest
from django.core.management import call_command
from django.test import override_settings
from rest_framework.test import APIClient

from communities.models import Community, DirectConversation, DirectMessage


@pytest.mark.django_db
@override_settings(DEBUG=True)
def test_sample_seed_is_repeatable_and_guest_can_read_direct_messages():
    guest = APIClient()
    community_id = guest.post("/communities", {"name": "My study group"}).data["id"]

    call_command("seed_sample_communities", guest_community=community_id)
    call_command("seed_sample_communities", guest_community=community_id)

    assert (
        Community.objects.filter(
            name__in=("NYU Calculus Study Circle", "Queens Biology Lab", "MIT Algorithms Club")
        ).count()
        == 3
    )
    assert DirectConversation.objects.count() == 2
    assert DirectMessage.objects.count() == 2
    assert len(guest.get(f"/communities/{community_id}/members").data["items"]) == 2
    assert {item["other_name"] for item in guest.get("/dms").data["items"]} == {
        "Maya",
        "Jordan",
    }
