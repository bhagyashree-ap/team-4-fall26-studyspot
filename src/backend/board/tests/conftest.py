import itertools

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from accounts.models import Account
from spots.models import StudySpot


@pytest.fixture(autouse=True)
def guest_access(settings):
    settings.CHAT_GUEST_ACCESS = True


@pytest.fixture
def guest_client():
    def create():
        client = APIClient(enforce_csrf_checks=True)
        response = client.get("/board/access")
        assert response.status_code == 200
        client.credentials(HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value)
        return client

    return create


@pytest.fixture
def account_client():
    sequence = itertools.count()

    def create(kind="student", *, active=True, staff=False):
        suffix = next(sequence)
        user = get_user_model().objects.create_user(
            username=f"auth0|board-{suffix}", is_active=active, is_staff=staff
        )
        account = Account.objects.create(
            user=user,
            account_type=kind,
            username=f"board_student_{suffix}" if kind == "student" else "",
            business_name=f"Board Cafe {suffix}" if kind == "business" else "",
            email=f"private-{suffix}@example.edu",
        )
        client = APIClient()
        client.force_authenticate(user=user)
        return client, account

    return create


@pytest.fixture
def spot():
    return StudySpot.objects.create(
        id="board:StableID",
        name="Board Test Library",
        category="public_library",
        borough="Manhattan",
        latitude=40.73,
        longitude=-73.99,
    )


@pytest.fixture
def draft():
    return {
        "kind": "question",
        "title": "Where can we study calculus?",
        "body": "Looking for a quiet place.\nWe study integrals on Tuesdays.",
        "tags": [
            {"kind": "subject", "value": "Calculus"},
            {"kind": "university", "value": "New York University"},
        ],
    }
