"""Tests for the dataset loader.

``data/spots.json`` is the source of truth and the ``spots`` table is a
rebuildable projection of it, so what matters here is that the projection ends
up exactly matching the snapshot, including for records the snapshot drops.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from spots.models import StudySpot

from .test_spots_api import RECORDS

pytestmark = pytest.mark.django_db


def write_snapshot(tmp_path: Path, records: list[dict[str, Any]]) -> Path:
    path = tmp_path / "spots.json"
    path.write_text(json.dumps(records), encoding="utf-8")
    return path


def load(path: Path) -> None:
    call_command("load_spots", dataset=path)


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
        # The table is a projection, so an upsert would wrongly keep rows the
        # importer no longer produces.
        load(write_snapshot(tmp_path, RECORDS))
        load(write_snapshot(tmp_path, RECORDS[:2]))
        assert StudySpot.objects.count() == 2
        assert not StudySpot.objects.filter(pk="dohmh:grumpy").exists()

    def test_an_empty_snapshot_empties_the_table(self, tmp_path: Path) -> None:
        load(write_snapshot(tmp_path, RECORDS))
        load(write_snapshot(tmp_path, []))
        assert StudySpot.objects.count() == 0

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
