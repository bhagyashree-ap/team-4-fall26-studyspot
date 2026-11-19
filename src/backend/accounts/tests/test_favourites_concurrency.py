from __future__ import annotations

import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from queue import Queue
from threading import Barrier, Event
from typing import Any

import pytest
from django.core.management.base import CommandError
from django.db import connection, transaction
from django.test import Client

from accounts.models import Account, AccountType, Favourite
from spots.models import StudySpot
from spots.tests.test_load_spots import load, write_snapshot
from spots.tests.test_spots_api import RECORDS

from . import test_favourites_api as api
from .test_accounts_api import Token, bearer

pytestmark = pytest.mark.django_db(transaction=True)
auth0 = api.auth0
signing_key = api.signing_key
token = api.token
student = api.student
spots = api.spots


def connected(action: Callable[[], Any], pids: Queue[int]) -> Any:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET statement_timeout = '15s'")
            cursor.execute("SELECT pg_backend_pid()")
            pids.put(cursor.fetchone()[0])
        return action()
    finally:
        connection.close()


def wait_for_blocked(pid: int) -> None:
    deadline = time.monotonic() + 10
    with connection.cursor() as cursor:
        while time.monotonic() < deadline:
            cursor.execute("SELECT cardinality(pg_blocking_pids(%s)) > 0", [pid])
            if cursor.fetchone()[0]:
                return
    raise AssertionError(f"Database connection {pid} did not reach the expected lock")


@pytest.mark.parametrize("method", ["put", "delete"])
def test_overlapping_identical_mutations_converge(
    student: Account, spots: list[StudySpot], token: Token, method: str
) -> None:
    path = f"/favourites/{spots[0].pk}"
    access_token = token()
    if method == "delete":
        Favourite.objects.create(account=student, spot=spots[0])
    pids: Queue[int] = Queue()
    start = Barrier(3)

    def mutate() -> int:
        start.wait(timeout=10)
        return getattr(Client(), method)(path, **bearer(access_token)).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        with transaction.atomic():
            if method == "put":
                StudySpot.objects.select_for_update().get(pk=spots[0].pk)
            else:
                Favourite.objects.select_for_update().get(account=student, spot=spots[0])
            futures = [pool.submit(connected, mutate, pids) for _ in range(2)]
            workers = [pids.get(timeout=10) for _ in range(2)]
            start.wait(timeout=10)
            for pid in workers:
                wait_for_blocked(pid)
        assert [future.result(timeout=15) for future in futures] == [204, 204]
    assert Favourite.objects.filter(account=student, spot=spots[0]).count() == (
        1 if method == "put" else 0
    )


def test_save_waiting_on_spot_observes_a_completed_removal(
    client: Any, student: Account, spots: list[StudySpot], token: Token
) -> None:
    Favourite.objects.create(account=student, spot=spots[0])
    path = f"/favourites/{spots[0].pk}"
    access_token = token()
    pids: Queue[int] = Queue()
    with ThreadPoolExecutor(max_workers=1) as pool:
        with transaction.atomic():
            StudySpot.objects.select_for_update().get(pk=spots[0].pk)
            saved = pool.submit(
                connected, lambda: Client().put(path, **bearer(access_token)).status_code, pids
            )
            wait_for_blocked(pids.get(timeout=10))
            assert client.delete(path, **bearer(access_token)).status_code == 204
        assert saved.result(timeout=15) == 204
    assert Favourite.objects.filter(account=student, spot=spots[0]).count() == 1


def test_refresh_waits_for_save_then_cascades_the_absent_spot(
    tmp_path: Path, student: Account, spots: list[StudySpot], token: Token
) -> None:
    snapshot = write_snapshot(tmp_path, RECORDS[1:])
    access_token = token()
    saved = Event()
    release = Event()
    pids: Queue[int] = Queue()

    def save_before_commit() -> int:
        with transaction.atomic():
            response = Client().put(f"/favourites/{spots[0].pk}", **bearer(access_token))
            saved.set()
            assert release.wait(timeout=10)
        return response.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        saving = pool.submit(connected, save_before_commit, pids)
        pids.get(timeout=10)
        try:
            assert saved.wait(timeout=10)
            refreshing = pool.submit(connected, lambda: load(snapshot), pids)
            wait_for_blocked(pids.get(timeout=10))
        finally:
            release.set()
        assert saving.result(timeout=15) == 204
        refreshing.result(timeout=15)
    assert not StudySpot.objects.filter(pk=spots[0].pk).exists()
    assert not Favourite.objects.exists()


def test_refresh_checks_owned_identifier_collisions_after_acquiring_its_lock(
    tmp_path: Path, student: Account, spots: list[StudySpot], token: Token
) -> None:
    owner = api.create_account("auth0|owner", AccountType.BUSINESS)
    owned_record = {**RECORDS[0], "id": "listing:concurrent", "category": "cafe"}
    snapshot = write_snapshot(
        tmp_path,
        [{**RECORDS[0], "name": "Refreshed"}, {**owned_record, "name": "Not the owner's name"}],
    )
    Favourite.objects.create(account=student, spot=spots[0])
    access_token = token()
    pids: Queue[int] = Queue()

    with ThreadPoolExecutor(max_workers=1) as pool:
        with transaction.atomic():
            owned = StudySpot.objects.create(**owned_record, owner=owner)
            response = Client().put(f"/favourites/{owned.pk}", **bearer(access_token))
            assert response.status_code == 204
            previous_spots = list(StudySpot.objects.values())
            previous_favourites = list(Favourite.objects.values())
            refreshing = pool.submit(connected, lambda: load(snapshot), pids)
            wait_for_blocked(pids.get(timeout=10))
        with pytest.raises(CommandError, match="business-owned"):
            refreshing.result(timeout=15)

    assert list(StudySpot.objects.values()) == previous_spots
    assert list(Favourite.objects.values()) == previous_favourites


@pytest.mark.parametrize("next_writer", ["save", "refresh"])
def test_refresh_serializes_saves_and_other_refreshes(
    tmp_path: Path, student: Account, spots: list[StudySpot], token: Token, next_writer: str
) -> None:
    first = write_snapshot(tmp_path, [{**RECORDS[1], "name": "Refreshed"}])
    second = tmp_path / "second.json"
    second.write_text("[]", encoding="utf-8")
    access_token = token()
    pids: Queue[int] = Queue()
    with connection.cursor() as cursor:
        cursor.execute(
            "CREATE FUNCTION favourites_test_pause_write() RETURNS trigger LANGUAGE plpgsql "
            "AS $$ BEGIN PERFORM pg_advisory_xact_lock(20261029); RETURN NEW; END; $$"
        )
        cursor.execute(
            "CREATE TRIGGER favourites_test_pause_write BEFORE INSERT OR UPDATE ON spots "
            "FOR EACH ROW EXECUTE FUNCTION favourites_test_pause_write()"
        )
        cursor.execute("SELECT pg_advisory_lock(20261029)")
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            try:
                refreshing = pool.submit(connected, lambda: load(first), pids)
                wait_for_blocked(pids.get(timeout=10))

                def action() -> Any:
                    if next_writer == "save":
                        return (
                            Client()
                            .put(f"/favourites/{spots[0].pk}", **bearer(access_token))
                            .status_code
                        )
                    return load(second)

                following = pool.submit(connected, action, pids)
                wait_for_blocked(pids.get(timeout=10))
            finally:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_advisory_unlock(20261029)")
            refreshing.result(timeout=15)
            result = following.result(timeout=15)
        if next_writer == "save":
            assert result == 404
            assert list(StudySpot.objects.values_list("pk", flat=True)) == [RECORDS[1]["id"]]
        else:
            assert not StudySpot.objects.exists()
        assert not Favourite.objects.exists()
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(20261029)")
            cursor.execute("DROP TRIGGER favourites_test_pause_write ON spots")
            cursor.execute("DROP FUNCTION favourites_test_pause_write()")


@pytest.mark.parametrize("first_writer", ["save", "delete"])
def test_owned_listing_deletion_serializes_with_favourite_saves(
    student: Account, token: Token, first_writer: str
) -> None:
    owner = api.create_account("auth0|delete-owner", AccountType.BUSINESS)
    owned = StudySpot.objects.create(
        **{**RECORDS[0], "id": "listing:delete-race", "category": "cafe"}, owner=owner
    )
    # Profile synchronization must not serialize the requests on a shared username.
    student_token = token(**{api.NAMESPACE + "username": student.username})
    owner_token = token(sub=owner.user.username, **{api.NAMESPACE + "username": owner.username})
    pids: Queue[int] = Queue()

    def save() -> int:
        return Client().put(f"/favourites/{owned.pk}", **bearer(student_token)).status_code

    def delete() -> int:
        return (
            Client(raise_request_exception=False)
            .delete(f"/listings/{owned.pk}", **bearer(owner_token))
            .status_code
        )

    with ThreadPoolExecutor(max_workers=1) as pool:
        with transaction.atomic():
            first, following = (save, delete) if first_writer == "save" else (delete, save)
            assert first() == 204
            waiting = pool.submit(connected, following, pids)
            wait_for_blocked(pids.get(timeout=10))
        assert waiting.result(timeout=15) == (204 if first_writer == "save" else 404)

    assert not StudySpot.objects.filter(pk=owned.pk).exists()
    assert not Favourite.objects.filter(spot_id=owned.pk).exists()
