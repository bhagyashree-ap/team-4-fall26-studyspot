"""The sample seed is repeatable and its DMs reach the active local guest."""

import pytest
from django.core.management import call_command
from django.test import override_settings

from communities.models import Community, DirectConversation, DirectMessage


@pytest.mark.django_db
@override_settings(DEBUG=True)
def test_sample_seed_is_repeatable_and_guest_can_read_direct_messages(existing_guest_community):
    guest, community_id = existing_guest_community

    call_command("seed_sample_communities", guest_community=community_id)
    models = (Community, DirectConversation, DirectMessage)
    counts = [model.objects.count() for model in models]
    assert Community.objects.filter(name="NYU Calculus Study Circle").exists()

    call_command("seed_sample_communities", guest_community=community_id)
    assert [model.objects.count() for model in models] == counts
    assert len(guest.get(f"/communities/{community_id}/members").data["items"]) == 2
    assert {item["other_name"] for item in guest.get("/dms").data["items"]} == {
        "Maya Chen",
        "Jordan Rivera",
    }
