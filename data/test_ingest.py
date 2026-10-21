"""Tests for the NYC Open Data importer.

These run against ``fixtures/``, a trimmed copy of what the Socrata datasets
actually return, so the suite never depends on NYC Open Data being up and CI
needs no network. The fixture keeps the awkward records the backend's own
fixtures warn about -- an accented name, a name carrying SQL ``LIKE`` wildcards,
a branch with no address, an older extract with no 2020 NTA column, a facility
type the importer excludes on purpose -- because those are the records a mapping
quietly gets wrong.

``fixtures/cafes.json`` is eleven inspection rows describing eight
establishments, which is the shape of ``43nn-pn8j`` in miniature. Six of the
eight are real records, chosen because each is a case that has to be handled:
one closed at its most recent inspection, one closed years ago and clean since,
one with no geocode, two that hold a sidewalk licence and one that shares its
street address with somebody else's. The remaining two are written by hand for
cases the live data cannot supply -- an establishment whose ``boro`` is ``"0"``
*and* which is geocoded, and one geocoded into open water.

``fixtures/neighborhoods.json`` carries every NTA's code and name, and the
boundary geometry for only the five the fixture cafes fall in. The real response
is 4.5 MB of coastline and none of the rest of it is exercised.

``fixtures/osm_cafes.json`` is seven records in the shape ``osm.py`` writes, one
per branch of the join: one that matches a fixture establishment on name and
address, one that matches on name and proximity with no address at all, one that
matches nothing and is published (Caffe Reggio, the case the whole source exists
for), one that matches nothing but is 31 m from a fixture cafe at a *different*
street address and is published on that evidence, one 54 m from a fixture cafe
with no address to tell them apart and so dropped as ambiguous, and two outside
the city -- one in New Jersey inside the Overpass bounding box, one outside
``NYC_BOUNDS`` altogether.

What matters here is that the snapshot the importer writes is one the loader
accepts and the API can serve: twenty-one fields, five boroughs, nulls rather
than blanks, and identifiers that do not move when upstream edits a name.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import ingest
import pytest

FIXTURES = Path(__file__).resolve().parent / "fixtures"

#: The example record published in docs/source/api.md. The importer has to
#: reproduce it exactly: it is what the frontend, the API and the search index
#: were written against.
PUBLISHED_EXAMPLE = {
    "id": "facdb:eec118768e15a5e03d3354abda7b00da",
    "name": "125th Street Library",
    "category": "public_library",
    "address": "224 East 125 Street, New York, NY 10035",
    "neighborhood": "East Harlem (North)",
    "borough": "Manhattan",
    "latitude": 40.803027,
    "longitude": -73.934853,
    "university": "Touro University - Harlem",
    # FacDB's opname. The branch is named after its neighborhood and nothing
    # else in the record says which system runs it.
    "operator": "New York Public Library",
    # The fixture puts a free hotspot on this branch; see fixtures/wifi.json.
    "free_public_wifi": True,
    # A public library costs nothing to sit in.
    "no_purchase_needed": True,
    # normalize() leaves these for combine(), which is the only point that sees
    # every published spot including the curated ones.
    "subway_station": None,
    "subway_routes": None,
    "subway_metres": None,
    "subway_step_free": None,
    "nearby_spots": 0,
    # Nothing licenses a library to put tables on the pavement, so no facility
    # can match the seating join.
    "outdoor_seating": False,
    # OpenStreetMap is read for cafes alone, so all three are unrecorded here.
    # Null and not false: nobody has said this branch has no indoor seating,
    # which would be a strange thing to say about a library.
    "indoor_seating": None,
    "venue_wifi": None,
    "opening_hours": None,
}

#: The published vocabulary. `university_building` is a campus building a
#: student can work in, which FacDB has no equivalent for and only the curated
#: list supplies; `cafe` comes from the health department's `Coffee/Tea`
#: classification.
CATEGORIES = {
    "public_library",
    "special_library",
    "academic_library",
    "university_building",
    "cafe",
}
BOROUGHS = {"Manhattan", "Brooklyn", "Queens", "Bronx", "Staten Island"}


@pytest.fixture(scope="module")
def facilities() -> list[dict[str, Any]]:
    return ingest.fixture_rows(FIXTURES, "facilities")


@pytest.fixture(scope="module")
def names() -> dict[str, str]:
    return ingest.neighborhood_names(ingest.fixture_rows(FIXTURES, "neighborhoods"))


@pytest.fixture(scope="module")
def hotspots() -> list[dict[str, Any]]:
    return ingest.fixture_rows(FIXTURES, "wifi")


@pytest.fixture(scope="module")
def cafes() -> list[dict[str, Any]]:
    return ingest.fixture_rows(FIXTURES, "cafes")


@pytest.fixture(scope="module")
def outdoor_dining() -> list[dict[str, Any]]:
    return ingest.fixture_rows(FIXTURES, "outdoor_dining")


@pytest.fixture(scope="module")
def osm() -> list[dict[str, Any]]:
    return ingest.fixture_rows(FIXTURES, "osm_cafes")


@pytest.fixture(scope="module")
def areas() -> list[ingest.NtaArea]:
    """The boundary polygons, which is how a cafe gets placed.

    DOHMH publishes no 2020 NTA code, so unlike a facility a cafe cannot be
    located by a dictionary lookup. Only the five NTAs the fixture cafes fall in
    carry geometry.
    """
    return ingest.nta_areas(ingest.fixture_rows(FIXTURES, "neighborhoods"))


@pytest.fixture(scope="module")
def spots(
    facilities: list[dict[str, Any]],
    names: dict[str, str],
    hotspots: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """The facility half of the snapshot. Cafes have their own fixture below."""
    return ingest.normalize(facilities, [], names, hotspots)


@pytest.fixture(scope="module")
def cafe_spots(
    cafes: list[dict[str, Any]],
    names: dict[str, str],
    areas: list[ingest.NtaArea],
    outdoor_dining: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """The cafes with no OpenStreetMap read at all.

    Which is a state the importer supports rather than a contrivance: the OSM
    list is a committed file, and :func:`ingest.osm_cafes` warns and carries on
    without it. These records are what the snapshot held before the source was
    added, so the tests that predate it keep testing what they tested.
    """
    return [
        spot
        for spot in ingest.normalize(
            [], cafes, names, [], areas=areas, outdoor_dining=outdoor_dining
        )
        if spot["category"] == ingest.CAFE_CATEGORY
    ]


@pytest.fixture(scope="module")
def merged_cafe_spots(
    cafes: list[dict[str, Any]],
    names: dict[str, str],
    areas: list[ingest.NtaArea],
    outdoor_dining: list[dict[str, Any]],
    osm: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """The cafes with OpenStreetMap merged over them, which is what ships."""
    return [
        spot
        for spot in ingest.normalize(
            [], cafes, names, [], areas=areas, outdoor_dining=outdoor_dining, osm=osm
        )
        if spot["category"] == ingest.CAFE_CATEGORY
    ]


def upstream(facilities: list[dict[str, Any]], facname: str) -> dict[str, Any]:
    """One raw record, copied so a test can edit it without affecting others."""
    return dict(next(record for record in facilities if record["facname"] == facname))


def published(spots: list[dict[str, Any]], name: str) -> dict[str, Any]:
    return next(spot for spot in spots if spot["name"] == name)


def osm_key(address: dict[str, Any]) -> str:
    """The join key for an OSM cafe carrying only the address fields given."""
    return ingest.osm_address_key({"id": "n1", "name": "Test Cafe", **address})


class TestPublishedExample:
    def test_is_reproduced_field_for_field(self, spots: list[dict[str, Any]]) -> None:
        spot = next(spot for spot in spots if spot["id"] == PUBLISHED_EXAMPLE["id"])
        assert spot == PUBLISHED_EXAMPLE


class TestIdentifiers:
    def test_carry_the_source_prefix_and_the_upstream_key(
        self, facilities: list[dict[str, Any]], spots: list[dict[str, Any]]
    ) -> None:
        for spot in spots:
            prefix, _, digest = spot["id"].partition(":")
            assert prefix == "facdb"
            assert digest in {record["uid"] for record in facilities}

    def test_survive_an_upstream_edit_to_the_record(
        self, facilities: list[dict[str, Any]], names: dict[str, str]
    ) -> None:
        # The loader replaces the table wholesale, so an identifier derived from
        # a record's contents would delete and recreate every row the city
        # corrected a typo in.
        record = upstream(facilities, "125TH STREET LIBRARY")
        edited = {
            **record,
            "facname": "125TH STREET BRANCH LIBRARY",
            "address": "224 E 125 STREET",
            "latitude": "40.8030269999",
        }
        assert ingest.normalize([edited], [], names, [])[0]["id"] == PUBLISHED_EXAMPLE["id"]

    def test_a_repeated_upstream_key_is_an_error(
        self, facilities: list[dict[str, Any]], names: dict[str, str]
    ) -> None:
        record = upstream(facilities, "125TH STREET LIBRARY")
        with pytest.raises(ingest.IngestError, match="Duplicate identifier"):
            ingest.normalize([record, {**record, "facname": "SOMEWHERE ELSE"}], [], names, [])

    def test_a_record_without_an_upstream_key_is_an_error(
        self, facilities: list[dict[str, Any]], names: dict[str, str]
    ) -> None:
        record = upstream(facilities, "125TH STREET LIBRARY")
        del record["uid"]
        with pytest.raises(ingest.IngestError, match="no uid"):
            ingest.normalize([record], [], names, [])


class TestCategories:
    @pytest.mark.parametrize(
        ("facname", "expected"),
        [
            ("125TH STREET LIBRARY", "public_library"),
            # A club's collection. Kept apart from the public branches because
            # the difference is the one a reader cares about: many special
            # libraries are open by appointment or to members only.
            ("THE GROLIER CLUB OF NEW YORK", "special_library"),
            ("COLUMBIA UNIVERSITY BUTLER LIBRARY", "academic_library"),
            ("COLUMBIA UNIVERSITY", "university"),
        ],
    )
    def test_upstream_types_map_onto_the_published_vocabulary(
        self, facilities: list[dict[str, Any]], facname: str, expected: str
    ) -> None:
        assert ingest.category(upstream(facilities, facname)) == expected

    def test_every_published_category_is_in_the_vocabulary(
        self, spots: list[dict[str, Any]]
    ) -> None:
        assert {spot["category"] for spot in spots} <= CATEGORIES

    def test_a_residence_is_excluded_rather_than_published(
        self, spots: list[dict[str, Any]]
    ) -> None:
        # People live there. The fixture carries CUNY's chancellor's residence
        # because FacDB files it under higher education.
        assert ingest.category({"uid": "x", "factype": "UNIVERSITY RESIDENTIAL STRUCTURE"}) is None
        assert not [spot for spot in spots if "Residence" in spot["name"]]

    def test_an_unmapped_type_fails_loudly(self, facilities: list[dict[str, Any]]) -> None:
        # Mapping it to the nearest existing category would publish a guess and
        # hide the fact that FacDB changed.
        record = {**upstream(facilities, "125TH STREET LIBRARY"), "factype": "COWORKING SPACE"}
        with pytest.raises(ingest.IngestError, match="COWORKING SPACE"):
            ingest.category(record)


class TestBoroughs:
    def test_are_the_five_exact_names(self, spots: list[dict[str, Any]]) -> None:
        assert {spot["borough"] for spot in spots} == BOROUGHS

    def test_a_sixth_borough_is_an_error(self, facilities: list[dict[str, Any]]) -> None:
        record = {**upstream(facilities, "125TH STREET LIBRARY"), "boro": "YONKERS"}
        with pytest.raises(ingest.IngestError, match="not one of the five boroughs"):
            ingest.borough(record)


class TestAbsentValues:
    def test_a_branch_without_an_address_publishes_null(self, spots: list[dict[str, Any]]) -> None:
        # FacDB has no street address for this branch. A city and a zip code are
        # not an address, so the field is null rather than ", Brooklyn, NY".
        assert published(spots, "Cypress Hills Library")["address"] is None

    def test_an_older_extract_without_the_nta_column_publishes_null(
        self, spots: list[dict[str, Any]]
    ) -> None:
        assert published(spots, "Great Kills Library")["neighborhood"] is None

    def test_nothing_is_published_as_a_blank_string(self, spots: list[dict[str, Any]]) -> None:
        # The contract distinguishes null from blank and the API returns null,
        # so an empty string would assert that the source supplied one.
        for spot in spots:
            for field in ("address", "neighborhood", "university"):
                assert spot[field] is None or spot[field].strip() == spot[field] != ""

    def test_a_record_without_coordinates_is_skipped(
        self, facilities: list[dict[str, Any]], names: dict[str, str]
    ) -> None:
        record = {**upstream(facilities, "125TH STREET LIBRARY"), "latitude": "", "longitude": ""}
        assert ingest.normalize([record], [], names, []) == []

    def test_a_non_numeric_coordinate_is_an_error(
        self, facilities: list[dict[str, Any]], names: dict[str, str]
    ) -> None:
        record = {**upstream(facilities, "125TH STREET LIBRARY"), "latitude": "uptown"}
        with pytest.raises(ingest.IngestError, match="non-numeric latitude"):
            ingest.normalize([record], [], names, [])


class TestNeighborhoods:
    def test_are_2020_nta_names(self, spots: list[dict[str, Any]]) -> None:
        assert published(spots, "125th Street Library")["neighborhood"] == "East Harlem (North)"
        assert published(spots, "Columbia University Butler Library")["neighborhood"] == (
            "Morningside Heights"
        )

    def test_a_code_the_boundary_file_does_not_know_publishes_null(
        self, facilities: list[dict[str, Any]], names: dict[str, str]
    ) -> None:
        # The two datasets are revised separately. Publishing "MN9999" would put
        # a code where the contract promises a name.
        record = {**upstream(facilities, "125TH STREET LIBRARY"), "nta2020": "MN9999"}
        assert ingest.normalize([record], [], names, [])[0]["neighborhood"] is None


class TestUniversityIsProximity:
    def test_a_campus_is_an_anchor_and_not_a_spot(self, spots: list[dict[str, Any]]) -> None:
        # A FacDB campus is an administrative point for an institution rather
        # than a room -- nobody can sit down in a registration -- so it anchors
        # the label below without being published as somewhere to study.
        assert not [spot for spot in spots if spot["name"] == "Columbia University"]
        assert "university" not in {spot["category"] for spot in spots}

    def test_the_anchor_still_labels_what_is_near_it(self, spots: list[dict[str, Any]]) -> None:
        # Dropping the campus records must not drop the derivation they feed.
        assert published(spots, "Columbia University Butler Library")["university"] == (
            "Columbia University"
        )

    def test_a_spot_inside_the_radius_names_the_closest_campus(
        self, spots: list[dict[str, Any]]
    ) -> None:
        assert published(spots, "Columbia University Butler Library")["university"] == (
            "Columbia University"
        )

    def test_a_spot_with_no_campus_nearby_publishes_null(self, spots: list[dict[str, Any]]) -> None:
        assert published(spots, "The Grolier Club of New York")["university"] is None

    def test_a_name_that_mentions_a_university_is_not_enough(
        self, facilities: list[dict[str, Any]], names: dict[str, str]
    ) -> None:
        # Affiliation is never inferred from a name, an operator, or anything
        # else: only the curated campus list and a distance.
        far = {
            **upstream(facilities, "GREAT KILLS LIBRARY"),
            "facname": "COLUMBIA UNIVERSITY READING ROOM",
        }
        campus = upstream(facilities, "COLUMBIA UNIVERSITY")
        published_spots = ingest.normalize([far, campus], [], names, [])
        assert published(published_spots, "Columbia University Reading Room")["university"] is None

    def test_the_radius_is_500_metres(self) -> None:
        campus = ingest.Campus("Somewhere College", 40.8, -73.95)
        # Roughly 330 m and 670 m north of the campus.
        assert ingest.nearest_campus(40.803, -73.95, [campus]) == "Somewhere College"
        assert ingest.nearest_campus(40.806, -73.95, [campus]) is None

    def test_the_closest_of_several_campuses_wins(self) -> None:
        near = ingest.Campus("Near College", 40.8005, -73.95)
        far = ingest.Campus("Far College", 40.803, -73.95)
        assert ingest.nearest_campus(40.8, -73.95, [far, near]) == "Near College"

    def test_the_documented_distance_holds(self, facilities: list[dict[str, Any]]) -> None:
        library = upstream(facilities, "125TH STREET LIBRARY")
        campus = upstream(facilities, "TOURO UNIVERSITY - HARLEM")
        metres = ingest.haversine_metres(
            float(library["latitude"]),
            float(library["longitude"]),
            float(campus["latitude"]),
            float(campus["longitude"]),
        )
        assert 160 < metres < 180


class TestNames:
    @pytest.mark.parametrize(
        ("shouted", "expected"),
        [
            ("125TH STREET LIBRARY", "125th Street Library"),
            ("ST JOHN'S UNIVERSITY LIBRARY", "St John's University Library"),
            ("CUNY HUNTER COLLEGE", "CUNY Hunter College"),
            ("CUNY'S CHANCELLORS RESIDENCE", "CUNY's Chancellors Residence"),
            ("LIBRARY FOR ARTS & CULTURE", "Library for Arts & Culture"),
            ("JUILLIARD SCHOOL (THE)", "Juilliard School (The)"),
            ("AMERICAN ACAD MCALLISTER INST", "American Acad McAllister Inst"),
            ("FORDHAM UNIV (ROSE HILL-LINCOLN CTR)", "Fordham Univ (Rose Hill-Lincoln Ctr)"),
            ("NY COL OF PODIATRIC MEDICINE", "NY Col of Podiatric Medicine"),
            # FacDB truncates long names mid-word and writes middle initials
            # without one, so neither trailing "A" is an article.
            ("NEW YORK CONSERVATORY FOR DRAMATIC A", "New York Conservatory for Dramatic A"),
            ("STEPHEN A. SCHWARZMAN BUILDING", "Stephen A. Schwarzman Building"),
        ],
    )
    def test_shouted_upstream_names_become_readable(self, shouted: str, expected: str) -> None:
        assert ingest.title_case(shouted) == expected

    def test_accents_survive(self, spots: list[dict[str, Any]]) -> None:
        # The API folds case across the whole of Unicode, so "garcía" has to
        # match what is stored. Mangling the accent here would break that.
        assert published(spots, "Biblioteca Yolanda García")
        assert ingest.title_case("YOLANDA GARCÍA PARK") == "Yolanda García Park"

    def test_sql_wildcards_are_left_alone(self, spots: list[dict[str, Any]]) -> None:
        # `?name=` matches `%` and `_` literally, so the importer must not
        # rewrite or escape them -- the API's filter is what handles them.
        spot = published(spots, "100% Coffee Reading Room")
        assert "%" in spot["name"]
        assert ingest.title_case("100% COFFEE_HOUSE") == "100% Coffee_house"

    def test_punctuation_between_words_is_kept(self, spots: list[dict[str, Any]]) -> None:
        assert published(spots, "Inwood Library–Joseph and Sheila Rosenblatt Building")


class TestSnapshot:
    def test_every_record_is_exactly_the_contract(self, spots: list[dict[str, Any]]) -> None:
        for spot in spots:
            assert tuple(spot) == ingest.CONTRACT_FIELDS

    def test_coordinates_are_rounded_to_six_places(self, spots: list[dict[str, Any]]) -> None:
        for spot in spots:
            assert spot["latitude"] == round(spot["latitude"], 6)
            assert spot["longitude"] == round(spot["longitude"], 6)
            assert -90 <= spot["latitude"] <= 90
            assert -180 <= spot["longitude"] <= 180

    def test_the_order_does_not_depend_on_the_upstream_order(
        self,
        facilities: list[dict[str, Any]],
        names: dict[str, str],
        hotspots: list[dict[str, Any]],
    ) -> None:
        # Socrata pages in whatever order it likes, and a reordered snapshot is
        # a diff of every line.
        assert ingest.normalize(list(reversed(facilities)), [], names, hotspots) == (
            ingest.normalize(facilities, [], names, hotspots)
        )

    def test_rerunning_writes_the_same_bytes(
        self,
        facilities: list[dict[str, Any]],
        names: dict[str, str],
        hotspots: list[dict[str, Any]],
        tmp_path: Path,
    ) -> None:
        first, second = tmp_path / "first.json", tmp_path / "second.json"
        for path in (first, second):
            ingest.write_snapshot(path, ingest.normalize(facilities, [], names, hotspots))
        assert first.read_bytes() == second.read_bytes()

    def test_a_record_outside_the_contract_is_an_error(self) -> None:
        with pytest.raises(ingest.IngestError, match="does not match the shared contract"):
            ingest.validate([{**PUBLISHED_EXAMPLE, "wifi": True}])


class TestCommandLine:
    def test_the_fixture_run_needs_no_network(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def refuse(*args: Any, **kwargs: Any) -> None:
            raise AssertionError("the fixture run reached the network")

        monkeypatch.setattr(ingest.urllib.request, "urlopen", refuse)
        output = tmp_path / "spots.json"
        assert ingest.main(["--fixtures", str(FIXTURES), "--output", str(output)]) == 0

        written = json.loads(output.read_text("utf-8"))
        # Nine published facility records -- eleven mapped, less the two
        # campuses, which anchor the proximity label without being spots -- and
        # five cafes from eleven inspection rows: eight establishments, less one
        # closed at its most recent inspection, one with no geocode and one
        # geocoded into open water. Plus two cafes only OpenStreetMap knows
        # about, of the seven records in that fixture: two enriched a DOHMH
        # establishment instead of being published, one was ambiguous and two
        # are outside the city. Plus the curated buildings, which are read from
        # the repository rather than from the network.
        assert len(written) == 9 + 5 + 2 + len(ingest.curated_spots())

    def test_a_missing_fixture_directory_is_reported_not_raised(self, tmp_path: Path) -> None:
        assert ingest.main(["--fixtures", str(tmp_path / "absent")]) == 1


@pytest.fixture(scope="module")
def snapshot() -> list[dict[str, Any]]:
    return json.loads((Path(__file__).resolve().parent / "spots.json").read_text("utf-8"))


class TestCommittedSnapshot:
    """The snapshot in version control, which is what deployments load."""

    def test_holds_real_records(self, snapshot: list[dict[str, Any]]) -> None:
        assert len(snapshot) > 100

    def test_matches_the_contract_the_loader_enforces(self, snapshot: list[dict[str, Any]]) -> None:
        ingest.validate(snapshot)
        assert {spot["borough"] for spot in snapshot} <= BOROUGHS
        assert {spot["category"] for spot in snapshot} <= CATEGORIES

    def test_is_sorted_and_unique_by_identifier(self, snapshot: list[dict[str, Any]]) -> None:
        identifiers = [spot["id"] for spot in snapshot]
        assert identifiers == sorted(identifiers)
        assert len(set(identifiers)) == len(identifiers)


@pytest.fixture
def curated() -> list[dict[str, Any]]:
    return ingest.curated_spots()


class TestCuratedBuildings:
    """The hand-maintained NYU list, which FacDB has no equivalent for.

    FacDB registers NYU as an institution and its schools as administrative
    points; none of them is a building a student can sit down in. These records
    are the only campus study space in the snapshot, so what matters is that a
    hand-edited file still satisfies the contract the loader enforces.
    """

    def test_every_record_matches_the_contract(self, curated: list[dict[str, Any]]) -> None:
        for spot in curated:
            assert tuple(spot) == ingest.CONTRACT_FIELDS

    def test_identifiers_carry_the_source_prefix(self, curated: list[dict[str, Any]]) -> None:
        # `nyu:` rather than `facdb:`, and a colon rather than a hyphen, so the
        # source stays parseable for anything that splits on the separator.
        for spot in curated:
            assert spot["id"].startswith("nyu:")

    def test_the_institution_is_named_rather_than_inferred(
        self, curated: list[dict[str, Any]]
    ) -> None:
        # For an open-data record `university` is the nearest campus within
        # 500 m. For these it is the institution whose building it is, which is
        # the stronger claim the contract allows for a campus record.
        for spot in curated:
            assert spot["university"] == "New York University"

    def test_a_missing_file_is_an_error(self, tmp_path: Path) -> None:
        with pytest.raises(ingest.IngestError, match="No curated building list"):
            ingest.curated_spots(tmp_path / "absent.json")

    def test_a_json_object_is_an_error(self, tmp_path: Path) -> None:
        path = tmp_path / "curated.json"
        path.write_text('{"id": "nyu:x"}', encoding="utf-8")
        with pytest.raises(ingest.IngestError, match="JSON array"):
            ingest.curated_spots(path)

    def test_a_missing_field_names_the_record(self, tmp_path: Path) -> None:
        path = tmp_path / "curated.json"
        path.write_text(json.dumps([{"id": "nyu:x", "name": "X"}]), encoding="utf-8")
        with pytest.raises(ingest.IngestError, match="nyu:x.*missing"):
            ingest.curated_spots(path)

    def test_a_field_outside_the_contract_is_an_error(
        self, tmp_path: Path, curated: list[dict[str, Any]]
    ) -> None:
        # A tenth field fails the load rather than being dropped, so the
        # importer refuses it where the record can still be named.
        record = {**curated[0], "wifi": True}
        path = tmp_path / "curated.json"
        path.write_text(json.dumps([record]), encoding="utf-8")
        with pytest.raises(
            ingest.IngestError, match="outside the shared contract|outside the contract"
        ):
            ingest.curated_spots(path)

    def test_key_order_is_rebuilt_rather_than_trusted(self, tmp_path: Path) -> None:
        # validate() compares key order, and a hand-edited file has no reason
        # to preserve it.
        reversed_record = {
            field: value
            for field, value in reversed(
                list(
                    {
                        "id": "nyu:x",
                        "name": "X",
                        "category": "university_building",
                        "address": None,
                        "neighborhood": None,
                        "borough": "Manhattan",
                        "latitude": 40.73,
                        "longitude": -73.99,
                        "university": "New York University",
                        "operator": "New York University",
                        "free_public_wifi": False,
                        "no_purchase_needed": True,
                        "subway_station": None,
                        "subway_routes": None,
                        "subway_metres": None,
                        "subway_step_free": None,
                        "nearby_spots": 0,
                        "outdoor_seating": False,
                        "indoor_seating": None,
                        "venue_wifi": None,
                        "opening_hours": None,
                    }.items()
                )
            )
        }
        path = tmp_path / "curated.json"
        path.write_text(json.dumps(reversed_record and [reversed_record]), encoding="utf-8")

        assert tuple(ingest.curated_spots(path)[0]) == ingest.CONTRACT_FIELDS


class TestCombine:
    def test_both_sources_reach_the_snapshot(
        self, spots: list[dict[str, Any]], curated: list[dict[str, Any]]
    ) -> None:
        merged = ingest.combine(spots, curated)

        assert len(merged) == len(spots) + len(curated)
        assert any(spot["id"].startswith("facdb:") for spot in merged)
        assert any(spot["id"].startswith("nyu:") for spot in merged)

    def test_the_curated_record_wins_an_identifier_collision(
        self, spots: list[dict[str, Any]], curated: list[dict[str, Any]]
    ) -> None:
        # The prefixes make this impossible in practice; keeping the wrong one
        # silently would be worse than preferring the deliberate record.
        clash = {**curated[0], "id": spots[0]["id"]}

        merged = ingest.combine(spots, [clash])

        assert len(merged) == len(spots)
        assert next(s for s in merged if s["id"] == clash["id"])["name"] == clash["name"]

    def test_the_result_is_sorted_by_identifier(
        self, spots: list[dict[str, Any]], curated: list[dict[str, Any]]
    ) -> None:
        merged = ingest.combine(spots, curated)

        assert [spot["id"] for spot in merged] == sorted(spot["id"] for spot in merged)

    def test_a_curated_record_breaking_the_contract_fails_the_merge(
        self, spots: list[dict[str, Any]], curated: list[dict[str, Any]]
    ) -> None:
        broken = {**curated[0], "borough": ""}

        with pytest.raises(ingest.IngestError, match="empty borough"):
            ingest.combine(spots, [broken])


class TestFreePublicWifi:
    """The one amenity the open data can support.

    The claim is narrow on purpose: a free hotspot the city publishes sits
    within 25 m. It is not "this place has Wi-Fi", because a campus building's
    Wi-Fi needs the university's credentials and the city has no reason to know
    about it.
    """

    def test_a_hotspot_on_the_spot_counts(self, spots: list[dict[str, Any]]) -> None:
        assert published(spots, "125th Street Library")["free_public_wifi"] is True

    def test_a_hotspot_a_metre_away_counts(self, spots: list[dict[str, Any]]) -> None:
        assert published(spots, "Columbia University Butler Library")["free_public_wifi"] is True

    def test_a_hotspot_beyond_the_radius_does_not(self, spots: list[dict[str, Any]]) -> None:
        # The fixture puts one 40 m from this branch, outside the 25 m radius.
        # Widening the radius is what turns the field from "Wi-Fi here" into
        # "a kiosk somewhere on the block".
        assert published(spots, "Cypress Hills Library")["free_public_wifi"] is False

    def test_a_spot_with_no_hotspot_nearby_is_false(self, spots: list[dict[str, Any]]) -> None:
        assert published(spots, "Great Kills Library")["free_public_wifi"] is False

    def test_an_ungeocoded_hotspot_is_ignored(
        self, facilities: list[dict[str, Any]], names: dict[str, str]
    ) -> None:
        # The real dataset carries rows with no coordinates; they cannot place
        # anything and must not crash the import.
        rows = [{"objectid": "x", "latitude": None, "longitude": None}]
        assert all(
            spot["free_public_wifi"] is False
            for spot in ingest.normalize(facilities, [], names, rows)
        )

    def test_the_value_is_always_a_boolean(self, spots: list[dict[str, Any]]) -> None:
        # The loader writes a BooleanField; None would be rejected at load time.
        assert all(isinstance(spot["free_public_wifi"], bool) for spot in spots)

    def test_curated_campus_buildings_are_false(self) -> None:
        # They have Wi-Fi; it needs NYU credentials. The field answers whether
        # anyone can use it.
        assert all(spot["free_public_wifi"] is False for spot in ingest.curated_spots())

    def test_the_radius_is_tight_enough_to_mean_something(self) -> None:
        assert ingest.WIFI_RADIUS_METRES <= 50.0


class TestCafes:
    """DOHMH Restaurant Inspection Results, the source for the ``cafe`` category.

    FacDB is a register of city facilities, so it holds libraries and campuses
    and not one cafe. The city does not operate cafes, but it does inspect them,
    and the inspector records what each one serves -- which is the question the
    category asks.
    """

    def by_name(self, spots: list[dict[str, Any]], name: str) -> dict[str, Any]:
        return next(spot for spot in spots if spot["name"] == name)

    def test_an_establishment_becomes_a_cafe(self, cafe_spots: list[dict[str, Any]]) -> None:
        spot = self.by_name(cafe_spots, "Leon's Bagels")

        assert spot["category"] == "cafe"
        assert spot["borough"] == "Manhattan"
        # `building` and `street` are separate columns upstream, joined here.
        assert spot["address"] == "169 Thompson Street, NY 10012"

    def test_the_identifier_names_the_source(self, cafe_spots: list[dict[str, Any]]) -> None:
        assert all(spot["id"].startswith("dohmh:") for spot in cafe_spots)

    def test_the_identifier_is_the_upstream_permit_number(
        self, cafe_spots: list[dict[str, Any]]
    ) -> None:
        # `camis` is DOHMH's own key for an establishment and survives a
        # renaming, a re-geocode and every later inspection. The previous
        # source had no such key, so the identifier was a hash of name and
        # address: renaming a cafe deleted it and created a stranger.
        assert self.by_name(cafe_spots, "Leon's Bagels")["id"] == "dohmh:50037080"

    def test_the_identifier_survives_an_upstream_edit_to_the_record(
        self,
        cafes: list[dict[str, Any]],
        names: dict[str, str],
        areas: list[ingest.NtaArea],
    ) -> None:
        edited = [
            {**row, "dba": "RENAMED OVERNIGHT"} if row["camis"] == "50037080" else row
            for row in cafes
        ]
        spots = ingest.normalize([], edited, names, [], areas=areas)

        assert self.by_name(spots, "Renamed Overnight")["id"] == "dohmh:50037080"

    def test_shouted_names_are_title_cased(self, cafe_spots: list[dict[str, Any]]) -> None:
        # DOHMH stores them upper case, as FacDB does.
        assert self.by_name(cafe_spots, "Mee Sum Cafe")["name"] == "Mee Sum Cafe"

    def test_the_log_is_folded_to_one_record_per_establishment(
        self, cafes: list[dict[str, Any]], cafe_spots: list[dict[str, Any]]
    ) -> None:
        # The dataset is one row per inspection: the fixture's eleven rows
        # describe eight establishments, of which five can be published.
        assert len(cafes) == 11
        assert len(ingest.establishments(cafes)) == 8
        assert len(cafe_spots) == 5
        assert len({spot["id"] for spot in cafe_spots}) == 5

    def test_the_most_recent_inspection_is_the_one_published(
        self, cafes: list[dict[str, Any]]
    ) -> None:
        rows = [row for row in cafes if row["camis"] == "50037080"]
        assert len(rows) > 1, "the fixture must hold more than one inspection of this one"

        latest = ingest.establishments(cafes)["50037080"]
        assert latest["inspection_date"] == max(row["inspection_date"] for row in rows)

    def test_a_cafe_closed_at_its_most_recent_inspection_is_dropped(
        self, cafe_spots: list[dict[str, Any]]
    ) -> None:
        # Publishing it would send a student to a locked door.
        assert not [spot for spot in cafe_spots if spot["name"] == "Momo Ashi"]

    def test_a_cafe_closed_years_ago_and_clean_since_is_published(
        self, cafes: list[dict[str, Any]], cafe_spots: list[dict[str, Any]]
    ) -> None:
        # The closure test reads the most recent inspection only. A place shut
        # for a week in 2023 and inspected cleanly since is open.
        history = [row for row in cafes if row["camis"] == "50114980"]
        assert any(ingest.CLOSURE_ACTION.search(row["action"]) for row in history)

        assert self.by_name(cafe_spots, "787 Coffee")["category"] == "cafe"

    def test_a_reopening_is_not_read_as_a_closure(self) -> None:
        # "Establishment re-opened by DOHMH" is the record of a place opening
        # again. A substring test for "closed" that is not anchored on the word
        # would be fine here, but a `LIKE '%Closed%'` is not: the dataset also
        # carries "re-closed", with a lower-case c.
        assert ingest.CLOSURE_ACTION.search("Establishment Closed by DOHMH.")
        assert ingest.CLOSURE_ACTION.search("Establishment re-closed by DOHMH.")
        assert not ingest.CLOSURE_ACTION.search("Establishment re-opened by DOHMH.")
        assert not ingest.CLOSURE_ACTION.search("Violations were cited in the following area(s).")

    def test_an_establishment_without_a_geocode_is_dropped(
        self, cafe_spots: list[dict[str, Any]]
    ) -> None:
        # Not an error: the register is maintained for inspections rather than
        # for mapping, and a row that cannot be placed is simply not a spot.
        assert not [spot for spot in cafe_spots if spot["name"] == "Cafe Grumpy"]

    def test_a_geocode_outside_every_neighborhood_is_dropped(
        self, cafe_spots: list[dict[str, Any]]
    ) -> None:
        # Inside the bounding box and out in the harbour. Nothing places it,
        # and the contract requires a borough.
        assert not [spot for spot in cafe_spots if spot["name"] == "Out in the Harbour"]

    def test_the_neighborhood_comes_from_the_boundary_polygon(
        self, cafe_spots: list[dict[str, Any]]
    ) -> None:
        # DOHMH publishes an `nta` column, but it is the 2010 vintage -- four
        # characters where a 2020 code is six -- so it cannot be joined to the
        # 2020 names the rest of the snapshot uses. The coordinates can.
        assert self.by_name(cafe_spots, "Leon's Bagels")["neighborhood"] == "Greenwich Village"
        assert self.by_name(cafe_spots, "Joe Coffee Company")["neighborhood"] == (
            "Brooklyn Heights"
        )

    def test_the_borough_comes_from_the_polygon_and_not_from_boro(
        self, cafe_spots: list[dict[str, Any]]
    ) -> None:
        # DOHMH's `boro` is "0" for a handful of establishments. The polygon
        # answers the same question and is never blank, so it is what the
        # record carries.
        spot = self.by_name(cafe_spots, "Borough Says Zero")
        assert spot["borough"] == "Manhattan"
        assert spot["neighborhood"] == "Chinatown-Two Bridges"

    def test_every_cafe_matches_the_contract(self, cafe_spots: list[dict[str, Any]]) -> None:
        for spot in cafe_spots:
            assert tuple(spot) == ingest.CONTRACT_FIELDS

    def test_the_category_is_the_health_department_s_own(self) -> None:
        # The whole of the category test. Reading the name instead is guessing,
        # and guessing is what published 1,652 bars and pizzerias as cafes.
        assert ingest.CAFES_WHERE == "cuisine_description = 'Coffee/Tea'"

    def test_mapping_cafes_without_the_boundaries_is_an_error(
        self, cafes: list[dict[str, Any]], names: dict[str, str]
    ) -> None:
        # The alternative default is dropping every cafe for want of a borough,
        # which looks exactly like upstream having no coffee shops today.
        with pytest.raises(ingest.IngestError, match="NTA boundaries"):
            ingest.normalize([], cafes, names, [])


class TestOutdoorSeating:
    """Dining Out NYC, demoted from a category to an attribute.

    A sidewalk licence says a business puts tables on the pavement. It says
    nothing about what the business sells, which is why treating it as the
    definition of a cafe published "Good Bar" and "Koronet Pizza" as places to
    study. It is a perfectly good source for one boolean.
    """

    def by_name(self, spots: list[dict[str, Any]], name: str) -> dict[str, Any]:
        return next(spot for spot in spots if spot["name"] == name)

    def test_a_matching_licence_sets_the_attribute(self, cafe_spots: list[dict[str, Any]]) -> None:
        assert self.by_name(cafe_spots, "Leon's Bagels")["outdoor_seating"] is True
        assert self.by_name(cafe_spots, "Joe Coffee Company")["outdoor_seating"] is True

    def test_a_licence_at_the_same_address_under_another_name_does_not(
        self, cafe_spots: list[dict[str, Any]]
    ) -> None:
        # The case the strictness is for. The fixture puts a licence at Mee Sum
        # Cafe's address held by "Someone Else Restaurant", which is what 28 of
        # these look like in the live data: a different business in the same
        # building. Crediting the cafe with it would be a false statement about
        # a real place.
        assert self.by_name(cafe_spots, "Mee Sum Cafe")["outdoor_seating"] is False

    def test_no_match_is_false_rather_than_missing(self, cafe_spots: list[dict[str, Any]]) -> None:
        # False means no licence matched, not that there is nowhere to sit. The
        # model's help_text says so; the contract has no third state.
        assert all(isinstance(spot["outdoor_seating"], bool) for spot in cafe_spots)
        assert self.by_name(cafe_spots, "787 Coffee")["outdoor_seating"] is False

    def test_a_facility_never_carries_it(self, spots: list[dict[str, Any]]) -> None:
        # Nothing licenses a library to put tables on the pavement.
        assert all(spot["outdoor_seating"] is False for spot in spots)

    def test_the_whole_snapshot_agrees(self, snapshot: list[dict[str, Any]]) -> None:
        # Only cafes can carry it, so a true on anything else means the join
        # has started matching on something it should not.
        for spot in snapshot:
            if spot["outdoor_seating"]:
                assert spot["category"] == "cafe", spot["id"]

    def test_only_issued_sidewalk_licences_are_requested(self) -> None:
        # A licence applied for and never granted is not seating, and a roadway
        # licence is a structure in a parking lane rather than somewhere to sit
        # with a laptop.
        assert "license_status = 'Issued'" in ingest.OUTDOOR_DINING_WHERE
        assert "license_type = 'Sidewalk'" in ingest.OUTDOOR_DINING_WHERE

    def test_the_two_registers_spell_an_address_differently(self) -> None:
        # DOHMH stores "169" + "THOMPSON STREET"; Dining Out stores "169
        # THOMPSON STREET". Neither is wrong and they must still match.
        assert ingest.match_key("169 THOMPSON STREET") == ingest.match_key("169 Thompson St")
        assert ingest.match_key("355 5 AVENUE") == ingest.match_key("355 5th Ave")
        assert ingest.match_key("30 WEST 25 ST") == ingest.match_key("30 W 25th Street")
        # Punctuation is noise in a match key and kept in a published name.
        assert ingest.match_key("TETE-A-TETE") == ingest.match_key("Tete A Tete")

    def test_a_distant_licence_is_rejected(
        self, cafes: list[dict[str, Any]], names: dict[str, str], areas: list[ingest.NtaArea]
    ) -> None:
        # The backstop. It fires on nothing in the live data, and is here so
        # that a re-geocode cannot quietly move a licence across town and have
        # it still match on name and address.
        moved = [
            {**row, "latitude": "40.55", "longitude": "-74.05"}
            if row.get("assumed_name_s") == "LEON'S BAGELS"
            else row
            for row in ingest.fixture_rows(FIXTURES, "outdoor_dining")
        ]
        spots = ingest.normalize([], cafes, names, [], areas=areas, outdoor_dining=moved)

        assert self.by_name(spots, "Leon's Bagels")["outdoor_seating"] is False


class TestCafesAreNotAttachedToCampuses:
    """A cafe is a third place in its own right.

    A library beside a campus is plausibly *its* library; the cafe on the same
    corner is just a cafe. The field would also have been unreliable: FacDB
    stores one point per institution whatever its size, so no radius separates
    the universities students attend from the vocational schools nobody is
    looking for.
    """

    def test_a_cafe_beside_a_campus_has_no_university(
        self, cafes: list[dict[str, Any]], names: dict[str, str], areas: list[ingest.NtaArea]
    ) -> None:
        # A campus placed on top of the first fixture cafe, so proximity cannot
        # be the reason the field is empty.
        first = ingest.normalize([], cafes, names, [], areas=areas)[0]
        campus = {
            "uid": "campus-on-the-doorstep",
            "facname": "RIGHT NEXT DOOR UNIVERSITY",
            "facsubgrp": "COLLEGES OR UNIVERSITIES",
            "factype": "4-YEAR INDEPENDENT",
            "boro": "MANHATTAN",
            "latitude": str(first["latitude"]),
            "longitude": str(first["longitude"]),
        }

        spots = ingest.normalize([campus], cafes, names, [], areas=areas)
        for spot in spots:
            if spot["category"] == ingest.CAFE_CATEGORY:
                assert spot["university"] is None

    def test_a_facility_beside_the_same_campus_still_gets_one(
        self, facilities: list[dict[str, Any]], names: dict[str, str]
    ) -> None:
        # The rule is about cafes, not about switching the derivation off.
        spots = ingest.normalize(facilities, [], names, [])
        assert any(spot["university"] for spot in spots if spot["category"] != "university")


class TestOperator:
    """The one field that connects a branch to its library system.

    A branch is named after its neighborhood -- "Howard Beach", "Fresh
    Meadows" -- so without this nothing in the record says who runs it, and
    asking for the Queens Public Library branches could not find them.
    """

    def test_a_branch_names_its_system(self, spots: list[dict[str, Any]]) -> None:
        assert published(spots, "125th Street Library")["operator"] == "New York Public Library"

    def test_it_is_not_title_cased(self, facilities: list[dict[str, Any]]) -> None:
        # Upstream already capitalises this field, unlike facname, so running
        # it through title_case() would only make it worse.
        record = {**upstream(facilities, "125TH STREET LIBRARY"), "opname": "NYU Tamiment Library"}
        assert ingest.operator(record) == "NYU Tamiment Library"

    def test_a_record_without_one_publishes_null(
        self, facilities: list[dict[str, Any]], names: dict[str, str]
    ) -> None:
        record = {**upstream(facilities, "125TH STREET LIBRARY")}
        record.pop("opname", None)
        assert ingest.normalize([record], [], names, [])[0]["operator"] is None

    def test_a_cafe_has_none(self, cafe_spots: list[dict[str, Any]]) -> None:
        # Dining Out carries the licence holder -- "CGM-LLNR LLC" where the
        # trading name is "JEAN'S" -- which is a registration rather than an
        # operator anyone would search for.
        assert all(spot["operator"] is None for spot in cafe_spots)

    def test_it_is_part_of_the_contract(self, spots: list[dict[str, Any]]) -> None:
        assert "operator" in ingest.CONTRACT_FIELDS
        for spot in spots:
            assert tuple(spot) == ingest.CONTRACT_FIELDS


class TestCostFollowsTheCategory:
    """Derived at import time and stored, like every other derived field here.

    It was briefly computed in the API serializer instead, on the argument that
    a column could drift from the category beside it. Prerendering the detail
    pages disproved that: those are built from this snapshot, where the field
    did not exist, so every library's page said a purchase was expected.
    `free_public_wifi` and `university` are derived and stored for the same
    reason -- the snapshot is regenerated as a unit and cannot drift from
    itself.
    """

    def test_a_library_costs_nothing(self, spots: list[dict[str, Any]]) -> None:
        assert published(spots, "125th Street Library")["no_purchase_needed"] is True

    def test_a_cafe_expects_a_purchase(self, cafe_spots: list[dict[str, Any]]) -> None:
        assert all(spot["no_purchase_needed"] is False for spot in cafe_spots)

    def test_it_matches_the_category_everywhere(self, snapshot: list[dict[str, Any]]) -> None:
        for spot in snapshot:
            expected = spot["category"] in ingest.NO_PURCHASE_CATEGORIES
            assert spot["no_purchase_needed"] is expected, spot["id"]

    def test_an_unmapped_category_is_not_claimed_free(
        self, facilities: list[dict[str, Any]], names: dict[str, str]
    ) -> None:
        # The set is an allowlist, so a category added to the vocabulary has to
        # be decided about rather than defaulting to free.
        assert "coworking_space" not in ingest.NO_PURCHASE_CATEGORIES


class TestCoordinatesMustBeInTheCity:
    """Upstream geocoding fails in a narrower way than the model checks for.

    Dining Out placed "Enzo's of Arthur Ave" -- a real address in the Bronx --
    at 42.126441,-70.848088, which is in Massachusetts Bay. Latitude and
    longitude were both valid, the borough said Bronx, and the record passed
    every check: it would have appeared in the Atlantic on a map and been given
    a nearest subway 284 km away.
    """

    def test_a_facility_outside_the_city_is_skipped(
        self, facilities: list[dict[str, Any]], names: dict[str, str]
    ) -> None:
        record = {
            **upstream(facilities, "125TH STREET LIBRARY"),
            "latitude": "42.126441",
            "longitude": "-70.848088",
        }
        assert ingest.normalize([record], [], names, []) == []

    def test_a_cafe_outside_the_city_is_dropped(
        self,
        cafes: list[dict[str, Any]],
        areas: list[ingest.NtaArea],
        outdoor_dining: list[dict[str, Any]],
    ) -> None:
        # Massachusetts Bay. The DOHMH geocodes that miss the box are 0,0 and
        # out-of-state zips rather than this, but the check is the same one and
        # a cafe must not survive it either.
        record = {**cafes[0], "latitude": "42.126441", "longitude": "-70.848088"}
        index = ingest.outdoor_dining_index(outdoor_dining)

        assert ingest.cafe_coordinates(record) is None
        assert ingest.cafe_spot(record["camis"], record, areas, index) is None

    def test_a_spot_inside_it_is_kept(
        self, facilities: list[dict[str, Any]], names: dict[str, str]
    ) -> None:
        # The check must not be so tight that it drops real records.
        assert (
            len(ingest.normalize([upstream(facilities, "125TH STREET LIBRARY")], [], names, []))
            == 1
        )

    def test_the_committed_snapshot_is_entirely_inside_it(
        self, snapshot: list[dict[str, Any]]
    ) -> None:
        for spot in snapshot:
            assert ingest.in_new_york_city(spot["latitude"], spot["longitude"]), spot["id"]


class TestNearestSubway:
    """Derived in the importer, for the reason `no_purchase_needed` had to learn.

    The result cards are rendered from the API and the detail pages from the
    snapshot. Anything computed in one of those places is missing from the
    other, so it is computed here, which is the only point both read from.
    """

    STATIONS = [
        {
            "name": "W 4 St-Wash Sq",
            "routes": ["A", "B", "C", "D", "E", "F", "M"],
            "latitude": 40.732338,
            "longitude": -74.000495,
            "step_free": "full",
        },
        {
            "name": "Far Away",
            "routes": ["7"],
            "latitude": 40.75,
            "longitude": -73.87,
            "step_free": "none",
        },
    ]

    def spot(self, latitude: float, longitude: float) -> dict[str, Any]:
        return {**PUBLISHED_EXAMPLE, "latitude": latitude, "longitude": longitude}

    def test_the_closest_station_wins(self) -> None:
        spots = [self.spot(40.7295, -73.9973)]
        ingest.assign_subway(spots, self.STATIONS)

        assert spots[0]["subway_station"] == "W 4 St-Wash Sq"
        assert spots[0]["subway_metres"] < 500

    def test_the_lines_are_space_joined(self) -> None:
        # The way the MTA publishes them and the way a sign reads.
        spots = [self.spot(40.7295, -73.9973)]
        ingest.assign_subway(spots, self.STATIONS)

        assert spots[0]["subway_routes"] == "A B C D E F M"

    def test_a_spot_with_nothing_near_publishes_null(self) -> None:
        # Rather than a number nobody would act on: the furthest spot from any
        # station is 7.7 km away, on Staten Island.
        spots = [self.spot(40.55, -74.15)]
        ingest.assign_subway(spots, self.STATIONS)

        for field in ("subway_station", "subway_routes", "subway_metres", "subway_step_free"):
            assert spots[0][field] is None

    def test_accessibility_comes_through_unrounded(self) -> None:
        spots = [self.spot(40.7295, -73.9973)]
        ingest.assign_subway(spots, self.STATIONS)

        assert spots[0]["subway_step_free"] == "full"

    def test_no_stations_leaves_every_spot_null(self) -> None:
        # `just ingest` without `just ingest-subway` warns rather than failing.
        spots = [self.spot(40.7295, -73.9973)]
        ingest.assign_subway(spots, [])

        assert spots[0]["subway_station"] is None

    def test_the_snapshot_is_consistent(self, snapshot: list[dict[str, Any]]) -> None:
        # All four are set together or not at all.
        for spot in snapshot:
            present = [
                spot[field] is not None
                for field in (
                    "subway_station",
                    "subway_routes",
                    "subway_metres",
                    "subway_step_free",
                )
            ]
            assert len(set(present)) == 1, spot["id"]


class TestOpenStreetMapIsAdditive:
    """The OSM merge may only add; it may never change what DOHMH established.

    This is the property the whole change turns on. The cafe source has already
    been swapped once and it cost real records, so the join is written to add
    attributes and records and to be incapable of anything else.
    """

    def test_no_dohmh_cafe_is_lost(
        self,
        cafe_spots: list[dict[str, Any]],
        merged_cafe_spots: list[dict[str, Any]],
    ) -> None:
        before = {spot["id"] for spot in cafe_spots}
        after = {spot["id"] for spot in merged_cafe_spots}

        assert before <= after

    def test_nothing_but_the_three_osm_fields_changes_on_a_dohmh_cafe(
        self,
        cafe_spots: list[dict[str, Any]],
        merged_cafe_spots: list[dict[str, Any]],
    ) -> None:
        merged = {spot["id"]: spot for spot in merged_cafe_spots}

        for before in cafe_spots:
            after = merged[before["id"]]
            for field in ingest.CONTRACT_FIELDS:
                if field in ingest.OSM_FIELDS:
                    continue
                # nearby_spots is assigned by combine() and these records have
                # not been through it, so it is 0 on both sides here.
                assert after[field] == before[field], f"{before['id']}.{field}"

    def test_a_cafe_dohmh_files_under_another_cuisine_is_published(
        self, merged_cafe_spots: list[dict[str, Any]]
    ) -> None:
        """The regression this source was added to fix.

        Caffe Reggio has been on MacDougal Street since 1927. DOHMH records its
        cuisine as Italian, so filtering on Coffee/Tea loses it, and it went
        missing from the live site when the category moved onto DOHMH.
        """
        reggio = published(merged_cafe_spots, "Caffe Reggio")

        assert reggio["id"] == "osm:n90000003"
        assert reggio["category"] == ingest.CAFE_CATEGORY
        assert reggio["address"] == "119 MacDougal Street, NY 10012"
        assert reggio["neighborhood"] == "Greenwich Village"
        assert reggio["borough"] == "Manhattan"

    def test_an_added_cafe_matches_the_contract_exactly(
        self, merged_cafe_spots: list[dict[str, Any]]
    ) -> None:
        reggio = published(merged_cafe_spots, "Caffe Reggio")

        assert tuple(reggio) == ingest.CONTRACT_FIELDS

    def test_an_added_cafe_is_not_free_and_names_no_campus(
        self, merged_cafe_spots: list[dict[str, Any]]
    ) -> None:
        # A cafe is where you buy something, and a cafe is a third place in its
        # own right rather than somewhere reached through a campus. The same two
        # rules the DOHMH cafes follow.
        reggio = published(merged_cafe_spots, "Caffe Reggio")

        assert reggio["no_purchase_needed"] is False
        assert reggio["university"] is None

    def test_an_added_cafe_matches_no_sidewalk_licence(
        self, merged_cafe_spots: list[dict[str, Any]]
    ) -> None:
        # The licence join runs on DOHMH establishments and this is not one, so
        # false here means what it means everywhere: no licence matched. OSM's
        # own outdoor_seating tag is deliberately not read into it.
        reggio = published(merged_cafe_spots, "Caffe Reggio")

        assert reggio["outdoor_seating"] is False


class TestOpenStreetMapMatching:
    """Which OSM records join, which are published, and which are refused.

    A wrong join silently attaches one venue's attributes to another, which has
    already happened on this project once. So a match needs the name *and* the
    location, and the cases below are the ones that decide it.
    """

    def test_a_name_and_address_match_enriches_the_establishment(
        self, merged_cafe_spots: list[dict[str, Any]]
    ) -> None:
        # OSM's "Mee Sum Cafe" at 26 Pell Street is the fixture establishment of
        # that name at that address.
        mee_sum = published(merged_cafe_spots, "Mee Sum Cafe")

        assert mee_sum["id"].startswith(f"{ingest.CAFE_PREFIX}:")
        assert mee_sum["indoor_seating"] is True
        assert mee_sum["venue_wifi"] is True
        assert mee_sum["opening_hours"] == "Mo-Su 08:00-21:00"

    def test_a_name_match_without_an_address_still_enriches_when_it_is_close(
        self, merged_cafe_spots: list[dict[str, Any]]
    ) -> None:
        # 60 m away and no addr:street at all, which is 862 of the 2,978 records.
        # The name and the proximity together are the match.
        joe = published(merged_cafe_spots, "Joe Coffee Company")

        assert joe["id"].startswith(f"{ingest.CAFE_PREFIX}:")
        assert joe["venue_wifi"] is False
        assert joe["indoor_seating"] is False

    def test_a_recorded_no_survives_as_false_rather_than_becoming_unrecorded(
        self, merged_cafe_spots: list[dict[str, Any]]
    ) -> None:
        """The point of the whole exercise.

        ``internet_access = no`` is somebody who went and looked. Rounding it to
        null would throw away the only trustworthy negative in the snapshot --
        ``free_public_wifi = false`` means no *city* hotspot within 25 m, which
        is a different and much weaker statement.
        """
        joe = published(merged_cafe_spots, "Joe Coffee Company")

        assert joe["venue_wifi"] is False
        assert joe["venue_wifi"] is not None

    def test_an_unmatched_cafe_at_a_different_address_nearby_is_published(
        self, merged_cafe_spots: list[dict[str, Any]]
    ) -> None:
        """31 m from "Leon's Bagels" at 169 Thompson Street, and at 171.

        Proximity alone cannot tell a differently-spelled duplicate from the
        shop next door -- in the live data about half of each -- so the street
        address is what decides it. Two addresses are two storefronts.
        """
        gregorys = published(merged_cafe_spots, "Gregory's Coffee")

        assert gregorys["id"] == "osm:n90000005"
        assert gregorys["address"] == "171 Thompson Street, NY 10012"

    def test_an_unmatched_cafe_with_no_address_nearby_is_dropped(
        self, merged_cafe_spots: list[dict[str, Any]]
    ) -> None:
        """54 m from "Leon's Bagels" and carrying no address of its own.

        It might be that cafe under another name and it might be the one next
        door, and nothing here says which. Publishing it risks a second pin for
        one place; joining it risks crediting Leon's with somebody else's hours.
        """
        assert not [spot for spot in merged_cafe_spots if spot["name"] == "Starbucks"]

    def test_a_cafe_in_new_jersey_inside_the_bounding_box_is_dropped(
        self, merged_cafe_spots: list[dict[str, Any]]
    ) -> None:
        # The Overpass bounding box is a rectangle and the city is not: it
        # reaches into Essex County, and the cafe at Turtle Back Zoo in West
        # Orange is inside it and inside NYC_BOUNDS. The neighborhood polygons
        # are what actually keeps New Jersey out, as they do for DOHMH.
        assert not [spot for spot in merged_cafe_spots if spot["name"] == "Savanna Café"]

    def test_a_cafe_outside_the_city_bounds_is_dropped(
        self, merged_cafe_spots: list[dict[str, Any]]
    ) -> None:
        assert not [spot for spot in merged_cafe_spots if spot["name"] == "Upstate Roasters"]

    def test_two_establishments_of_one_name_nearby_join_to_neither(
        self, areas: list[ingest.NtaArea]
    ) -> None:
        """Two Starbucks either side of a street is the common case.

        Crediting one of them with the other's opening hours is a coin toss, so
        neither is credited and the record is reported as ambiguous.
        """
        cafes = [
            {**self.CAFE, "id": "dohmh:1", "latitude": 40.7295, "longitude": -73.9974},
            {**self.CAFE, "id": "dohmh:2", "latitude": 40.7296, "longitude": -73.9975},
        ]
        identities = {
            "dohmh:1": ingest.CafeIdentity(name="STARBUCKS", address="1 BROADWAY"),
            "dohmh:2": ingest.CafeIdentity(name="STARBUCKS", address="2 BROADWAY"),
        }
        records = [
            {
                "id": "n1",
                "name": "Starbucks",
                "latitude": 40.7295,
                "longitude": -73.9974,
                "house_number": None,
                "street": None,
                "postcode": None,
                "indoor_seating": True,
                "venue_wifi": True,
                "opening_hours": "Mo-Su 06:00-20:00",
            }
        ]

        added, merge = ingest.merge_osm_cafes(cafes, identities, records, areas)

        assert added == []
        assert merge == ingest.OsmMerge(enriched=0, added=0, ambiguous=1, unplaceable=0)
        assert all(cafe["venue_wifi"] is None for cafe in cafes)

    def test_one_establishment_claimed_by_two_osm_records_joins_to_neither_twice(
        self, areas: list[ingest.NtaArea]
    ) -> None:
        """The first claim stands and the second is ambiguous.

        Not "last write wins": that would make the snapshot depend on the order
        the committed file happens to be read in, and the second record is
        evidence that the first match was not as certain as it looked.
        """
        cafes = [{**self.CAFE, "id": "dohmh:1", "latitude": 40.7295, "longitude": -73.9974}]
        identities = {"dohmh:1": ingest.CafeIdentity(name="STARBUCKS", address="1 BROADWAY")}
        record = {
            "id": "n1",
            "name": "Starbucks",
            "latitude": 40.7295,
            "longitude": -73.9974,
            "house_number": None,
            "street": None,
            "postcode": None,
            "indoor_seating": True,
            "venue_wifi": None,
            "opening_hours": None,
        }

        added, merge = ingest.merge_osm_cafes(
            cafes, identities, [record, {**record, "id": "n2", "indoor_seating": False}], areas
        )

        assert added == []
        assert merge.enriched == 1
        assert merge.ambiguous == 1
        assert cafes[0]["indoor_seating"] is True

    def test_a_name_match_too_far_away_is_a_different_branch(
        self, areas: list[ingest.NtaArea]
    ) -> None:
        """ "Starbucks" 400 m away is a different Starbucks.

        There are over a hundred in the register and the name tells them apart
        not at all, which is why the name alone is never a match. 400 m is also
        past OSM_SAME_STOREFRONT_METRES, so this one is published rather than
        dropped: it is a cafe the snapshot does not have.
        """
        cafes = [{**self.CAFE, "id": "dohmh:1", "latitude": 40.7295, "longitude": -73.9974}]
        identities = {"dohmh:1": ingest.CafeIdentity(name="STARBUCKS", address="1 BROADWAY")}
        records = [
            {
                "id": "n1",
                "name": "Starbucks",
                # About 400 m north, still inside Greenwich Village.
                "latitude": 40.7331,
                "longitude": -73.9974,
                "house_number": "9",
                "street": "Broadway",
                "postcode": None,
                "indoor_seating": True,
                "venue_wifi": None,
                "opening_hours": None,
            }
        ]

        added, merge = ingest.merge_osm_cafes(cafes, identities, records, areas)

        assert merge.enriched == 0
        assert merge.added == 1
        assert cafes[0]["indoor_seating"] is None
        assert added[0]["id"] == "osm:n1"

    def test_the_radii_are_ordered_from_strictest_to_loosest(self) -> None:
        # A storefront can appear to move 68 m between the two registers (95th
        # percentile), the name alone is trusted to 150 m, and an address that
        # agrees is trusted to 200 m. Reordering any pair would change which
        # branch a record takes without changing a word of the logic.
        assert (
            ingest.OSM_SAME_STOREFRONT_METRES
            < ingest.OSM_NAME_MATCH_RADIUS_METRES
            < ingest.OSM_ADDRESS_MATCH_RADIUS_METRES
        )

    #: A published cafe record, as a starting point for the hand-built cases
    #: above. Only the fields the join reads matter; the rest are the contract.
    CAFE = {
        "id": "dohmh:0",
        "name": "Starbucks",
        "category": "cafe",
        "address": "1 Broadway, NY 10004",
        "neighborhood": "Greenwich Village",
        "borough": "Manhattan",
        "latitude": 40.7295,
        "longitude": -73.9974,
        "university": None,
        "operator": None,
        "free_public_wifi": False,
        "no_purchase_needed": False,
        "subway_station": None,
        "subway_routes": None,
        "subway_metres": None,
        "subway_step_free": None,
        "nearby_spots": 0,
        "outdoor_seating": False,
        "indoor_seating": None,
        "venue_wifi": None,
        "opening_hours": None,
    }


class TestThreeStateFields:
    """True, false and unrecorded are three answers, and stay three.

    Collapsing the third into the second is the mistake these fields exist to
    avoid, and it is the easy mistake: a truthiness test makes it silently.
    """

    def test_the_osm_fields_are_part_of_the_contract(self) -> None:
        assert set(ingest.OSM_FIELDS) <= set(ingest.CONTRACT_FIELDS)

    def test_a_cafe_with_no_osm_record_is_unrecorded_and_not_false(
        self, merged_cafe_spots: list[dict[str, Any]]
    ) -> None:
        leons = published(merged_cafe_spots, "Leon's Bagels")

        for field in ingest.OSM_FIELDS:
            assert leons[field] is None, field

    def test_a_library_is_unrecorded_and_not_false(self, spots: list[dict[str, Any]]) -> None:
        # OpenStreetMap is read for cafes alone. Null is the honest value:
        # nobody has said a branch has no indoor seating.
        for spot in spots:
            for field in ingest.OSM_FIELDS:
                assert spot[field] is None, f"{spot['id']}.{field}"

    def test_the_booleans_are_only_ever_true_false_or_none(
        self, snapshot: list[dict[str, Any]]
    ) -> None:
        for spot in snapshot:
            for field in ("indoor_seating", "venue_wifi"):
                assert spot[field] in (True, False, None), f"{spot['id']}.{field}"

    def test_opening_hours_is_the_raw_osm_string_or_null(
        self, snapshot: list[dict[str, Any]]
    ) -> None:
        # Stored as written. Turning it into an "open now" needs a timezone and
        # the public-holiday calendar the syntax can refer to, which is its own
        # piece of work.
        for spot in snapshot:
            hours = spot["opening_hours"]
            assert hours is None or (isinstance(hours, str) and hours.strip() == hours and hours)

    def test_a_non_boolean_in_the_committed_file_is_an_error(self) -> None:
        # The file is committed, so a hand-edit is exactly where a string lands
        # where a boolean belongs -- and "no" is truthy.
        with pytest.raises(ingest.IngestError, match="non-boolean venue_wifi"):
            ingest.osm_attributes({"id": "n1", "venue_wifi": "no"})

    def test_venue_wifi_is_not_free_public_wifi(self, snapshot: list[dict[str, Any]]) -> None:
        """Two different claims, and the snapshot proves they are not the same.

        One is the venue's own Wi-Fi as recorded by somebody who was there; the
        other is a hotspot the city publishes within 25 m of the point. If the
        two agreed everywhere, one of them would be redundant.
        """
        disagree = [
            spot
            for spot in snapshot
            if spot["venue_wifi"] is not None and spot["venue_wifi"] != spot["free_public_wifi"]
        ]

        assert disagree


class TestTheOsmCafeFile:
    """The committed cafe list, read the way the subway station list is."""

    def test_a_missing_file_is_a_warning_and_not_an_error(self, tmp_path: Path) -> None:
        # `just ingest` without `just ingest-osm` publishes DOHMH cafes with
        # three unrecorded fields, which is a smaller snapshot and not a broken
        # one.
        assert ingest.osm_cafes(tmp_path / "absent.json") == []

    def test_a_json_object_is_an_error(self, tmp_path: Path) -> None:
        path = tmp_path / "osm_cafes.json"
        path.write_text('{"id": "n1"}', encoding="utf-8")

        with pytest.raises(ingest.IngestError, match="array of cafes"):
            ingest.osm_cafes(path)

    def test_the_committed_file_is_the_shape_the_importer_reads(self) -> None:
        cafes = ingest.osm_cafes()

        assert cafes
        for cafe in cafes:
            assert set(cafe) == {
                "id",
                "name",
                "latitude",
                "longitude",
                "house_number",
                "street",
                "postcode",
                "indoor_seating",
                "venue_wifi",
                "opening_hours",
            }

    def test_every_identifier_is_a_node_or_a_way_and_has_no_slash(self) -> None:
        # A spot identifier becomes a URL path segment, so OSM's own
        # "node/3506087030" would be two segments and a 404.
        for cafe in ingest.osm_cafes():
            assert cafe["id"][0] in "nw"
            assert cafe["id"][1:].isdigit()

    def test_the_committed_snapshot_publishes_the_source(
        self, snapshot: list[dict[str, Any]]
    ) -> None:
        osm_spots = [spot for spot in snapshot if spot["id"].startswith(f"{ingest.OSM_PREFIX}:")]

        assert osm_spots
        assert all(spot["category"] == ingest.CAFE_CATEGORY for spot in osm_spots)

    def test_the_committed_snapshot_still_has_its_dohmh_cafes(
        self, snapshot: list[dict[str, Any]]
    ) -> None:
        """Additive: the OSM merge may not cost a DOHMH establishment.

        A floor rather than an exact count, deliberately. DOHMH is an
        inspection log that moves daily -- two runs an hour apart gave 16 and
        17 closures -- so pinning the published figure would make this fail
        because a coffee shop in Queens shut, which is not what it is testing.

        The exact property, before against after on one run, is asserted by
        `TestOpenStreetMapIsAdditive`, where both sides come from the same
        upstream snapshot and the number cannot drift between them.
        """
        dohmh = [spot for spot in snapshot if spot["id"].startswith(f"{ingest.CAFE_PREFIX}:")]

        assert len(dohmh) > 2000


class TestAPartialAddressIsNotAnAddress:
    """A street with no house number cannot decide whether two records are one door.

    Worse than useless: compared against "123 Broadway" it *disagrees*, and the
    merge reads a disagreement as evidence of two separate storefronts. So a
    partial address is no address, and the record joins on name and proximity
    like the 831 cafes that carry none at all.
    """

    def test_a_street_with_no_number_is_no_key(self) -> None:
        assert osm_key({"street": "Broadway"}) == ""

    def test_a_number_with_no_street_is_no_key(self) -> None:
        assert osm_key({"house_number": "123"}) == ""

    def test_both_together_are_a_key(self) -> None:
        assert osm_key({"house_number": "123", "street": "Broadway"}) == "123 BROADWAY"

    def test_the_key_folds_the_two_registers_onto_one_spelling(self) -> None:
        # DOHMH writes "MACDOUGAL ST" where OSM writes "MacDougal Street", and
        # neither is wrong. Street types, compass directions and ordinals are
        # folded before comparing; the key is never published.
        assert osm_key({"house_number": "119", "street": "MacDougal Street"}) == "119 MACDOUGAL ST"
        assert osm_key({"house_number": "1875", "street": "Utica Avenue"}) == "1875 UTICA AVE"
        assert osm_key({"house_number": "405", "street": "West 23rd Street"}) == "405 W 23 ST"

    def test_a_cafe_with_only_a_street_near_a_dohmh_cafe_is_not_published(
        self, areas: list[ingest.NtaArea]
    ) -> None:
        # Without this it would read as "a different address, therefore a
        # different storefront" and be published as a second pin.
        cafes = [{**TestOpenStreetMapMatching.CAFE, "id": "dohmh:1"}]
        identities = {"dohmh:1": ingest.CafeIdentity(name="STARBUCKS", address="1 BROADWAY")}
        records = [
            {
                "id": "n1",
                "name": "Some Other Cafe",
                "latitude": 40.7295,
                "longitude": -73.9974,
                "house_number": None,
                "street": "Broadway",
                "postcode": None,
                "indoor_seating": None,
                "venue_wifi": None,
                "opening_hours": None,
            }
        ]

        added, merge = ingest.merge_osm_cafes(cafes, identities, records, areas)

        assert added == []
        assert merge.ambiguous == 1


class TestCuratedBuildingsWinDuplicates:
    """A curated building beats the open-data row describing the same building.

    FacDB registers "New York University Libraries" as an academic library at
    Bobst's coordinates, 12 m from `nyu:bobst-library`, with the *building
    name* where a street address belongs and "LIU-New York University Campus"
    -- Long Island University -- as its campus. A search for "bobst" returned
    both, because the search vector includes the address.

    Every test below is about the two conditions that keep the rule from
    deleting records that are not duplicates.
    """

    #: A curated building, as `nyu_buildings.json` supplies it.
    BUILDING = {
        **TestOpenStreetMapMatching.CAFE,
        "id": "nyu:bobst-library",
        "name": "Elmer Holmes Bobst Library",
        "category": "academic_library",
        "address": "70 Washington Square South, New York, NY 10012",
        "no_purchase_needed": True,
        "operator": "New York University",
        "university": "New York University",
        "latitude": 40.7295,
        "longitude": -73.9974,
    }

    def near(self, **overrides: Any) -> dict[str, Any]:
        """An open-data record 12 m from the curated building."""
        return {
            **TestOpenStreetMapMatching.CAFE,
            "id": "facdb:generic",
            "name": "New York University Libraries",
            "category": "academic_library",
            "address": "Elmer H Bobst Library, New York, NY 10012",
            "latitude": 40.72949,
            "longitude": -73.99726,
            **overrides,
        }

    def test_the_building_recorded_twice_is_published_once(self) -> None:
        kept, dropped = ingest.drop_curated_duplicates([self.BUILDING, self.near()])

        assert [spot["id"] for spot in kept] == ["nyu:bobst-library"]
        assert dropped == [("New York University Libraries", "Elmer Holmes Bobst Library")]

    def test_a_cafe_in_the_same_building_is_not_a_duplicate(self) -> None:
        """The condition that protects nine real records.

        Nine non-curated records sit within 60 m of a curated building in the
        live data and every one is a cafe: Peet's Coffee @ NYU is 10 m from the
        Kimmel Center, Blank Street Coffee 26 m from Rogers Hall, The Uncommons
        24 m from the Global Center. They are cafes inside or beside the
        building, and they are separate study spots. A rule that went on
        distance alone would delete all nine to fix one duplicate.
        """
        cafe = self.near(id="dohmh:peets", name="Peet's Coffee @ NYU", category="cafe")

        kept, dropped = ingest.drop_curated_duplicates([self.BUILDING, cafe])

        assert dropped == []
        assert {spot["id"] for spot in kept} == {"nyu:bobst-library", "dohmh:peets"}

    def test_a_library_with_its_own_street_address_is_not_a_duplicate(self) -> None:
        """The condition that is easy to leave out, and costs a real record.

        *Two* academic libraries sit within 50 m of Bobst. The second is "NYU
        Tamiment Library" at 17 m -- the Tamiment Library and Robert F. Wagner
        Labor Archives, a named special collection on Bobst's tenth floor,
        publishing its own street address. It is a library someone might search
        for by name and it is not a duplicate of anything. Same category and
        well inside the radius, so only the address tells it apart.
        """
        tamiment = self.near(
            id="facdb:tamiment",
            name="NYU Tamiment Library",
            address="70 Washington Square South, New York, NY 10012",
            latitude=40.729437,
            longitude=-73.997217,
        )

        kept, dropped = ingest.drop_curated_duplicates([self.BUILDING, tamiment])

        assert dropped == []
        assert "facdb:tamiment" in {spot["id"] for spot in kept}

    def test_the_street_may_be_the_curated_records_own(self) -> None:
        # Tamiment is at Bobst's address, because it is on Bobst's tenth floor.
        # The test is whether the record claims an address, not whether the
        # address differs.
        assert self.BUILDING["address"] == "70 Washington Square South, New York, NY 10012"

    def test_a_record_with_no_address_at_all_is_dropped(self) -> None:
        # Same reasoning as the building name: a row that cannot say what
        # street it is on, sitting on a curated building of the same kind, has
        # recorded that building.
        kept, dropped = ingest.drop_curated_duplicates([self.BUILDING, self.near(address=None)])

        assert [spot["id"] for spot in kept] == ["nyu:bobst-library"]
        assert len(dropped) == 1

    def test_the_same_record_across_the_street_is_kept(self) -> None:
        # Two records of one category 200 m apart are two places.
        far = self.near(latitude=40.7313, longitude=-73.9974)

        kept, dropped = ingest.drop_curated_duplicates([self.BUILDING, far])

        assert dropped == []
        assert len(kept) == 2

    def test_a_curated_record_is_never_dropped_for_another_curated_record(self) -> None:
        # Two curated buildings can legitimately be metres apart, and neither
        # was written by the open-data importer.
        second = {**self.BUILDING, "id": "nyu:kimmel", "name": "Kimmel Center", "address": None}

        kept, dropped = ingest.drop_curated_duplicates([self.BUILDING, second])

        assert dropped == []
        assert len(kept) == 2

    def test_nothing_happens_without_a_curated_list(self) -> None:
        # `--fixtures` runs and most of the test suite map facilities alone.
        spots = [self.near()]

        kept, dropped = ingest.drop_curated_duplicates(spots)

        assert kept == spots
        assert dropped == []

    def test_combine_applies_it(self) -> None:
        spots = ingest.combine([self.near()], [self.BUILDING])

        assert [spot["id"] for spot in spots] == ["nyu:bobst-library"]

    def test_it_runs_before_the_neighbour_count(self) -> None:
        # A record about to be dropped must not be counted as somebody else's
        # neighbour, or the curated building reports a neighbour that is itself.
        spots = ingest.combine([self.near()], [self.BUILDING])

        assert spots[0]["nearby_spots"] == 0


class TestTheCommittedSnapshotHasNoCuratedDuplicates:
    def test_bobst_matches_exactly_one_record(self, snapshot: list[dict[str, Any]]) -> None:
        # Name *and* address, because the search vector weights both and the
        # duplicate carried "Bobst" in its address rather than its name.
        matching = [
            spot
            for spot in snapshot
            if "bobst" in f"{spot['name']} {spot['address'] or ''}".lower()
        ]

        assert [spot["id"] for spot in matching] == ["nyu:bobst-library"]

    def test_every_curated_building_survives(self, snapshot: list[dict[str, Any]]) -> None:
        curated = [spot for spot in snapshot if spot["id"].startswith(f"{ingest.CURATED_PREFIX}:")]

        assert len(curated) == len(ingest.curated_spots())

    def test_the_cafes_beside_the_curated_buildings_survive(
        self, snapshot: list[dict[str, Any]]
    ) -> None:
        # The nine the rule is written around. Named rather than counted, so a
        # future loosening of the rule names which one it deleted.
        names = {spot["name"] for spot in snapshot}

        for cafe in (
            "Peet's Coffee @ NYU",
            "Blank Street Coffee",
            "The Uncommons",
            "Think Coffee",
            "Tartinery",
            "Irving Farm New York",
            "Ariston Flowers & Cafe",
            "Colomba Bakery",
        ):
            assert cafe in names, cafe

    def test_nothing_non_curated_shares_a_category_and_a_doorstep(
        self, snapshot: list[dict[str, Any]]
    ) -> None:
        curated = [spot for spot in snapshot if spot["id"].startswith(f"{ingest.CURATED_PREFIX}:")]

        for building in curated:
            for spot in snapshot:
                if spot["id"].startswith(f"{ingest.CURATED_PREFIX}:"):
                    continue
                if spot["category"] != building["category"]:
                    continue
                metres = ingest.haversine_metres(
                    building["latitude"],
                    building["longitude"],
                    spot["latitude"],
                    spot["longitude"],
                )
                if metres <= ingest.CURATED_DUPLICATE_METRES:
                    # Survives only by claiming a street address of its own.
                    assert ingest.HOUSE_NUMBER.match(spot["address"] or ""), spot["id"]
