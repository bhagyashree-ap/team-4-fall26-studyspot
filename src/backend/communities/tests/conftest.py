import pytest
from rest_framework.test import APIClient

from communities.services import create_guest_community


@pytest.fixture
def existing_guest_community(db, settings):
    """A guest-owned group and browser session created before sign-in was required."""
    settings.CHAT_GUEST_DEMO = True
    owner = APIClient(enforce_csrf_checks=True)
    session = owner.session
    identity = "existing-guest"
    community = create_guest_community({"name": "Study group"}, identity, session.get_expiry_date())
    session["community_guest_id"] = identity
    session["guest_communities"] = [community.pk]
    session.save()
    owner.get("/admin/login/")
    owner.credentials(HTTP_X_CSRFTOKEN=owner.cookies["csrftoken"].value)
    return owner, community.pk
