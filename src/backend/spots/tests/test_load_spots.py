"""Tests for the dataset loader."""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
from typing import Any

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, connection

from accounts.models import Account, AccountType, Favourite
from accounts.tests.test_favourites_api import create_account
from spots.management.commands.load_spots import CONTRACT_FIELDS
from spots.models import StudySpot

from .test_spots_api import RECORDS

pytestmark = pytest.mark.django_db


def write_snapshot(tmp_path: Path, records: list[dict[str, Any]]) -> Path:
    path = tmp_path / "spots.json"
    path.write_text(json.dumps(records), encoding="utf-8")
    return path


def load(path: Path) -> None:
    call_command("load_spots", dataset=path)


@pytest.fixture
def owned_spot() -> StudySpot:
    user = get_user_model().objects.create(username="auth0|owner")
    owner = Account.objects.create(
        user=user, account_type=AccountType.BUSINESS, business_name="Corner Cafe"
    )
    return StudySpot.objects.create(
        id="listing:corner",
        name="Corner Cafe",
        category="cafe",
        borough="Manhattan",
        latitude=40.7259,
        longitude=-73.9946,
        owner=owner,
    )


class TestLoading:
    def test_writes_every_record(self, tmp_path: Path) -> None:
        load(write_snapshot(tmp_path, RECORDS))
        assert StudySpot.objects.count() == len(RECORDS)

    def test_is_repeatable(self, tmp_path: Path) -> None:
        path = write_snapshot(tmp_path, RECORDS)
        load(path)
        load(path)
        assert StudySpot.objects.count() == len(RECORDS)

    def test_drops_records_removed_upstream(self, tmp_path: Path) -> None:
        load(write_snapshot(tmp_path, RECORDS))
        load(write_snapshot(tmp_path, RECORDS[:2]))
        assert StudySpot.objects.count() == 2
        assert not StudySpot.objects.filter(pk="dohmh:grumpy").exists()

    def test_an_empty_snapshot_empties_the_table(self, tmp_path: Path) -> None:
        load(write_snapshot(tmp_path, RECORDS))
        load(write_snapshot(tmp_path, []))
        assert StudySpot.objects.count() == 0

    def test_keeps_listings_a_business_owns(self, tmp_path: Path, owned_spot: StudySpot) -> None:
        load(write_snapshot(tmp_path, []))

        assert list(StudySpot.objects.values_list("pk", flat=True)) == [owned_spot.pk]

    def test_a_record_without_a_university_loads(self, tmp_path: Path) -> None:
        # Snapshots produced before the field existed omit it entirely.
        record = {key: value for key, value in RECORDS[0].items() if key != "university"}
        load(write_snapshot(tmp_path, [record]))
        assert StudySpot.objects.get(pk=record["id"]).university is None

    @pytest.mark.parametrize("borough", ["brooklyn", "BROOKLYN", "  Staten   Island "])
    def test_borough_casing_and_spacing_are_normalized(self, tmp_path: Path, borough: str) -> None:
        load(write_snapshot(tmp_path, [{**RECORDS[0], "borough": borough}]))
        assert StudySpot.objects.get(pk=RECORDS[0]["id"]).borough in {
            "Brooklyn",
            "Staten Island",
        }


class TestRejection:
    def test_a_missing_file_is_an_error(self, tmp_path: Path) -> None:
        with pytest.raises(CommandError, match="No dataset at"):
            load(tmp_path / "absent.json")

    def test_a_json_object_is_an_error(self, tmp_path: Path) -> None:
        path = tmp_path / "spots.json"
        path.write_text('{"id": "facdb:bobst"}', encoding="utf-8")
        with pytest.raises(CommandError, match="JSON array"):
            load(path)

    def test_a_field_outside_the_contract_is_an_error(self, tmp_path: Path) -> None:
        # A field the model does not know about means the importer and the API
        # have drifted; dropping it silently would hide that.
        record = {**RECORDS[0], "wifi": True}
        with pytest.raises(CommandError, match="outside the shared contract"):
            load(write_snapshot(tmp_path, [record]))

    def test_a_borough_outside_the_five_is_an_error(self, tmp_path: Path) -> None:
        with pytest.raises(CommandError, match="is invalid"):
            load(write_snapshot(tmp_path, [{**RECORDS[0], "borough": "Yonkers"}]))

    def test_an_out_of_range_latitude_is_an_error(self, tmp_path: Path) -> None:
        with pytest.raises(CommandError, match="is invalid"):
            load(write_snapshot(tmp_path, [{**RECORDS[0], "latitude": 91.0}]))

    def test_a_rejected_snapshot_leaves_the_table_untouched(self, tmp_path: Path) -> None:
        load(write_snapshot(tmp_path, RECORDS))
        with pytest.raises(CommandError):
            load(write_snapshot(tmp_path, [{**RECORDS[0], "borough": "Yonkers"}]))
        assert StudySpot.objects.count() == len(RECORDS)


class TestEveryContractFieldIsWritten:
    """A field the loader accepts but never writes is worse than one it rejects.

    `operator` was added to the contract and to the loader's allowlist, and the
    model is built from an explicit keyword list, so it validated cleanly and
    was dropped on the floor. 1,916 rows loaded with the column null and
    nothing said so.
    """

    def test_no_contract_field_is_silently_dropped(self, db: None) -> None:
        from spots.management.commands.load_spots import CONTRACT_FIELDS, to_spot

        record = {
            "id": "facdb:everything",
            "name": "Every Field Set",
            "category": "public_library",
            "address": "1 Test Street, New York, NY 10001",
            "neighborhood": "Test Neighborhood",
            "borough": "Manhattan",
            "latitude": 40.75,
            "longitude": -73.99,
            "university": "Test University",
            "operator": "Test Operator",
            "free_public_wifi": True,
            "no_purchase_needed": True,
            "subway_station": "W 4 St-Wash Sq",
            "subway_routes": "A B C D E F M",
            "subway_metres": 409,
            "subway_step_free": "full",
            "nearby_spots": 41,
            "outdoor_seating": True,
            # The three-state fields, set to the two states the loader has to
            # carry without a default. A `False` reaching the model as null, or
            # a null reaching it as False, is exactly the silent drop this test
            # exists for.
            "indoor_seating": True,
            "venue_wifi": False,
            "opening_hours": "Mo-Fr 07:00-19:00; Sa-Su 08:00-18:00",
        }
        assert set(record) == CONTRACT_FIELDS, "the fixture must cover the whole contract"

        spot = to_spot(record, 0)

        for field in CONTRACT_FIELDS:
            assert getattr(spot, field) == record[field], f"{field} was not written"


class TestTheThreeStateFieldsLoadAsThreeStates:
    """`indoor_seating`, `venue_wifi` and `opening_hours` must not take a default.

    Every other boolean in the loader does -- `record.get("free_public_wifi",
    False)` -- because a snapshot written before that field existed should load
    as false. These three are the exception: false is a claim here, and a
    snapshot that does not mention them has to load as unknown. Getting this
    wrong would silently assert that nobody can sit inside anywhere and that no
    cafe in the city has Wi-Fi.
    """

    #: The contract as it stood before these three fields, which is what an
    #: older snapshot on disk looks like.
    OLDER_SNAPSHOT_RECORD = {
        "id": "facdb:older",
        "name": "Written Before The Fields Existed",
        "category": "public_library",
        "address": "1 Test Street, New York, NY 10001",
        "neighborhood": "Test Neighborhood",
        "borough": "Manhattan",
        "latitude": 40.75,
        "longitude": -73.99,
        "university": None,
        "operator": None,
        "free_public_wifi": False,
        "no_purchase_needed": True,
        "subway_station": None,
        "subway_routes": None,
        "subway_metres": None,
        "subway_step_free": None,
        "nearby_spots": 0,
        "outdoor_seating": False,
    }

    def test_a_snapshot_without_them_loads_as_unknown_and_not_as_false(self, db: None) -> None:
        from spots.management.commands.load_spots import to_spot

        spot = to_spot(dict(self.OLDER_SNAPSHOT_RECORD), 0)

        assert spot.indoor_seating is None
        assert spot.venue_wifi is None
        assert spot.opening_hours is None

    def test_an_explicit_false_survives_as_false(self, db: None) -> None:
        from spots.management.commands.load_spots import to_spot

        # The trustworthy negative: a contributor went and looked. Reading it
        # back as null would throw away the only Wi-Fi claim in the snapshot
        # worth anything -- a false `free_public_wifi` only ever meant that no
        # hotspot the city publishes is within 25 m.
        record = {**self.OLDER_SNAPSHOT_RECORD, "venue_wifi": False, "indoor_seating": False}

        spot = to_spot(record, 0)

        assert spot.venue_wifi is False
        assert spot.indoor_seating is False

    def test_an_explicit_null_is_accepted_rather_than_rejected(self, db: None) -> None:
        from spots.management.commands.load_spots import to_spot

        # full_clean() runs on every row, so a nullable field that was not
        # declared nullable on the model would fail here rather than at write
        # time. The importer writes these as null for about 90% of spots.
        record = {
            **self.OLDER_SNAPSHOT_RECORD,
            "indoor_seating": None,
            "venue_wifi": None,
            "opening_hours": None,
        }

        assert to_spot(record, 0).venue_wifi is None

    def test_opening_hours_is_stored_as_written(self, db: None) -> None:
        from spots.management.commands.load_spots import to_spot

        hours = "Mo-Fr 07:00-19:00; Sa-Su 08:00-18:00"
        record = {**self.OLDER_SNAPSHOT_RECORD, "opening_hours": hours}

        assert to_spot(record, 0).opening_hours == hours


class TestFavouriteSnapshotLifecycle:
    def test_retained_ids_keep_saved_links_and_absent_ids_cascade(self, tmp_path: Path) -> None:
        load(write_snapshot(tmp_path, RECORDS))
        account = create_account("auth0|student")
        kept = Favourite.objects.create(account=account, spot_id=RECORDS[0]["id"])
        Favourite.objects.create(account=account, spot_id=RECORDS[1]["id"])
        replacement = [
            {**RECORDS[0], "name": "Refreshed library"},
            {**RECORDS[2], "id": "facdb:new"},
        ]

        load(write_snapshot(tmp_path, replacement))

        assert set(StudySpot.objects.values_list("pk", flat=True)) == {
            RECORDS[0]["id"],
            "facdb:new",
        }
        current = Favourite.objects.get()
        assert current.pk == kept.pk
        assert current.created_at == kept.created_at
        assert current.spot.name == "Refreshed library"

    def test_empty_snapshot_cascades_imported_saved_links(self, tmp_path: Path) -> None:
        load(write_snapshot(tmp_path, RECORDS))
        account = create_account("auth0|student")
        Favourite.objects.create(account=account, spot_id=RECORDS[0]["id"])

        load(write_snapshot(tmp_path, []))

        assert not StudySpot.objects.exists()
        assert not Favourite.objects.exists()
        assert account.favourites.count() == 0

    @pytest.mark.parametrize("empty", [False, True])
    def test_owned_listings_and_saved_links_survive_snapshot_replacement(
        self, tmp_path: Path, owned_spot: StudySpot, empty: bool
    ) -> None:
        load(write_snapshot(tmp_path, RECORDS))
        account = create_account("auth0|student")
        retained = Favourite.objects.create(account=account, spot_id=RECORDS[0]["id"])
        Favourite.objects.create(account=account, spot_id=RECORDS[1]["id"])
        owned = Favourite.objects.create(account=account, spot=owned_spot)
        previous_owned = StudySpot.objects.values().get(pk=owned_spot.pk)
        records = (
            []
            if empty
            else [
                {**RECORDS[0], "name": "Refreshed library"},
                {**RECORDS[2], "id": "facdb:new"},
            ]
        )
        path = write_snapshot(tmp_path, records)
        output = StringIO()

        call_command("load_spots", dataset=path, stdout=output)

        assert set(StudySpot.objects.values_list("pk", flat=True)) == {
            owned_spot.pk,
            *(record["id"] for record in records),
        }
        assert StudySpot.objects.values().get(pk=owned_spot.pk) == previous_owned
        expected_favourites = [owned] if empty else [owned, retained]
        assert set(Favourite.objects.values_list("pk", flat=True)) == {
            favourite.pk for favourite in expected_favourites
        }
        for favourite in expected_favourites:
            current = Favourite.objects.get(pk=favourite.pk)
            assert current.created_at == favourite.created_at
            assert current.account_id == favourite.account_id
            assert current.spot_id == favourite.spot_id
        if not empty:
            refreshed = StudySpot.objects.get(pk=RECORDS[0]["id"])
            assert refreshed.name == "Refreshed library"
            assert refreshed.owner_id is None
        assert f"loaded {len(records)} spots from {path}" in output.getvalue()

    @pytest.mark.parametrize("collision_index", [0, 500])
    def test_owned_identifier_collision_leaves_spots_and_favourites_unchanged(
        self, tmp_path: Path, owned_spot: StudySpot, collision_index: int
    ) -> None:
        load(write_snapshot(tmp_path, RECORDS))
        account = create_account("auth0|student")
        Favourite.objects.create(account=account, spot_id=RECORDS[0]["id"])
        Favourite.objects.create(account=account, spot_id=RECORDS[1]["id"])
        Favourite.objects.create(account=account, spot=owned_spot)
        previous_spots = list(StudySpot.objects.values())
        previous_favourites = list(Favourite.objects.values())
        records = [
            {**RECORDS[0], "name": "Updated before collision"},
            *[{**RECORDS[0], "id": f"facdb:new-{index}"} for index in range(500)],
        ]
        records[collision_index] = {
            **RECORDS[0],
            "id": owned_spot.pk,
            "name": "Snapshot must not take ownership",
        }

        with pytest.raises(CommandError, match="business-owned"):
            load(write_snapshot(tmp_path, records))

        assert list(StudySpot.objects.values()) == previous_spots
        assert list(Favourite.objects.values()) == previous_favourites

    @pytest.mark.parametrize(
        "failure",
        ["invalid_last", "duplicate_nearby", "duplicate_across_batches", "owner", "owner_id"],
    )
    def test_rejected_snapshots_leave_spots_and_favourites_unchanged(
        self, tmp_path: Path, owned_spot: StudySpot, failure: str
    ) -> None:
        load(write_snapshot(tmp_path, RECORDS))
        account = create_account("auth0|student")
        Favourite.objects.create(account=account, spot_id=RECORDS[1]["id"])
        Favourite.objects.create(account=account, spot=owned_spot)
        previous_spots = list(StudySpot.objects.values())
        previous_favourites = list(Favourite.objects.values())
        records = [{**RECORDS[0], "id": f"facdb:replacement-{index}"} for index in range(501)]
        if failure == "invalid_last":
            records[-1]["latitude"] = 91
        elif failure == "duplicate_nearby":
            records[1]["id"] = records[0]["id"]
        elif failure == "duplicate_across_batches":
            records[-1]["id"] = records[0]["id"]
        else:
            records[-1][failure] = owned_spot.owner_id

        with pytest.raises(CommandError):
            load(write_snapshot(tmp_path, records))

        assert list(StudySpot.objects.values()) == previous_spots
        assert list(Favourite.objects.values()) == previous_favourites

    @pytest.mark.django_db(transaction=True)
    def test_later_write_failure_restores_prior_updates_deletions_and_saved_links(
        self, tmp_path: Path, owned_spot: StudySpot
    ) -> None:
        load(write_snapshot(tmp_path, RECORDS))
        account = create_account("auth0|student")
        Favourite.objects.create(account=account, spot_id=RECORDS[0]["id"])
        Favourite.objects.create(account=account, spot_id=RECORDS[1]["id"])
        Favourite.objects.create(account=account, spot=owned_spot)
        previous_spots = list(StudySpot.objects.values())
        previous_favourites = list(Favourite.objects.values())
        records = [
            {**RECORDS[0], "name": "Updated before failure"},
            *[{**RECORDS[0], "id": f"facdb:new-{index}"} for index in range(499)],
            {**RECORDS[0], "id": "facdb:rejected", "name": "Rejected by database"},
        ]
        with connection.cursor() as cursor:
            cursor.execute(
                "ALTER TABLE spots ADD CONSTRAINT favourites_test_write_failure "
                "CHECK (name <> 'Rejected by database')"
            )
        try:
            with pytest.raises(IntegrityError):
                load(write_snapshot(tmp_path, records))
        finally:
            with connection.cursor() as cursor:
                cursor.execute("ALTER TABLE spots DROP CONSTRAINT favourites_test_write_failure")

        assert list(StudySpot.objects.values()) == previous_spots
        assert list(Favourite.objects.values()) == previous_favourites

    def test_upsert_refreshes_every_mutable_field_including_unknown_values(
        self, tmp_path: Path
    ) -> None:
        original = {
            **RECORDS[0],
            "operator": "Original operator",
            "free_public_wifi": False,
            "no_purchase_needed": True,
            "subway_station": "Original station",
            "subway_routes": "A",
            "subway_metres": 100,
            "subway_step_free": "full",
            "nearby_spots": 1,
            "outdoor_seating": False,
            "indoor_seating": True,
            "venue_wifi": False,
            "opening_hours": "Mo-Fr 09:00-17:00",
        }
        replacement = {
            "id": original["id"],
            "name": "Refreshed cafe",
            "category": "cafe",
            "address": None,
            "neighborhood": None,
            "borough": "Brooklyn",
            "latitude": 40.7,
            "longitude": -73.9,
            "university": None,
            "operator": None,
            "free_public_wifi": True,
            "no_purchase_needed": False,
            "subway_station": None,
            "subway_routes": None,
            "subway_metres": None,
            "subway_step_free": None,
            "nearby_spots": 25,
            "outdoor_seating": True,
            "indoor_seating": False,
            "venue_wifi": True,
            "opening_hours": None,
        }
        assert set(original) == set(replacement) == CONTRACT_FIELDS
        load(write_snapshot(tmp_path, [original]))
        account = create_account("auth0|student")
        favourite = Favourite.objects.create(account=account, spot_id=original["id"])

        load(write_snapshot(tmp_path, [replacement]))

        current = StudySpot.objects.get(pk=original["id"])
        for field, value in replacement.items():
            assert getattr(current, field) == value, field
        assert Favourite.objects.get().pk == favourite.pk
