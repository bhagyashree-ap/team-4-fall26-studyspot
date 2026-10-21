"""Tests for the OpenStreetMap cafe source.

These never reach Overpass. ``fetch()`` is the one function that does and it is
exercised against a stubbed ``urlopen``, because the real thing is a
volunteer-run service that takes 45 seconds to answer and is rate-limited: a
suite that called it would be slow, flaky, and rude.

What matters here is the mapping from tags to the three published states. The
whole reason this source is read is that ``internet_access = no`` is a
trustworthy negative and an absent tag is not, so a test that only checked
"true becomes true" would miss the point entirely.
"""

from __future__ import annotations

import io
import json
import urllib.error
from pathlib import Path
from typing import Any

import osm
import pytest


def element(**tags: Any) -> dict[str, Any]:
    """One Overpass node with the given tags, at a point in Manhattan."""
    return {
        "type": "node",
        "id": 1,
        "lat": 40.7295,
        "lon": -73.9974,
        "tags": {"amenity": "cafe", "name": "Test Cafe", **tags},
    }


def enough(**tags: Any) -> list[dict[str, Any]]:
    """``MINIMUM_CAFES`` distinct nodes, the first carrying ``tags``.

    ``normalize`` refuses a result that looks truncated, so any test of the
    mapping has to hand it a plausible number of records. The first is the one
    under test; the rest are filler.
    """
    first = element(**tags)
    filler = [{**element(), "id": index} for index in range(2, osm.MINIMUM_CAFES + 2)]
    return [first, *filler]


def mapped(**tags: Any) -> dict[str, Any]:
    """The published record for one node carrying ``tags``."""
    return next(cafe for cafe in osm.normalize(enough(**tags)) if cafe["id"] == "n1")


class TestInternetAccessBecomesVenueWifi:
    """``internet_access`` is three answers and stays three.

    This is the field the change exists for. ``free_public_wifi`` is a non-null
    boolean whose false means "no hotspot the city publishes within 25 m" and
    has to be explained everywhere it appears; this one's false means a
    contributor looked and found no Wi-Fi, which is worth much more, and
    rounding the unrecorded 83% into it would destroy the difference.
    """

    @pytest.mark.parametrize("value", ["wlan", "yes", "wifi", "WLAN", " yes "])
    def test_a_recorded_yes_is_true(self, value: str) -> None:
        assert mapped(internet_access=value)["venue_wifi"] is True

    def test_a_recorded_no_is_false_and_not_none(self) -> None:
        assert mapped(internet_access="no")["venue_wifi"] is False

    def test_an_absent_tag_is_none_and_not_false(self) -> None:
        assert mapped()["venue_wifi"] is None

    def test_a_value_nobody_has_thought_about_is_none(self) -> None:
        # A mapping table rather than a truthiness test, so a new upstream value
        # reads as unknown instead of as a claim.
        assert mapped(internet_access="maybe")["venue_wifi"] is None

    @pytest.mark.parametrize("value", ["wired", "terminal"])
    def test_internet_that_is_not_wifi_is_unrecorded_rather_than_false(self, value: str) -> None:
        # `wired` is an ethernet port and `terminal` is a public computer.
        # Neither says whether there is also Wi-Fi, so neither is a no.
        assert mapped(internet_access=value)["venue_wifi"] is None

    def test_a_contributor_writing_prose_is_read_as_the_values_it_contains(self) -> None:
        # One record in the city carries "yes, wifi". Semicolon is the documented
        # separator and the comma is not, so both are split on.
        assert mapped(internet_access="yes, wifi")["venue_wifi"] is True

    def test_two_values_that_disagree_are_unrecorded(self) -> None:
        # Choosing one of them would be inventing an answer.
        assert mapped(internet_access="yes;no")["venue_wifi"] is None


class TestIndoorSeating:
    def test_a_recorded_yes_is_true(self) -> None:
        assert mapped(indoor_seating="yes")["indoor_seating"] is True

    def test_a_recorded_no_is_false(self) -> None:
        assert mapped(indoor_seating="no")["indoor_seating"] is False

    def test_an_absent_tag_is_none(self) -> None:
        assert mapped()["indoor_seating"] is None

    def test_outdoor_seating_is_not_read_into_it(self) -> None:
        # Two different questions, and the snapshot already has an
        # `outdoor_seating` field meaning something narrower and checkable: a
        # Dining Out NYC sidewalk licence matching a name and an address.
        record = mapped(outdoor_seating="yes")

        assert record["indoor_seating"] is None
        assert "outdoor_seating" not in record


class TestOpeningHours:
    def test_the_raw_string_is_published_as_written(self) -> None:
        # Not parsed, and deliberately not turned into an "open now": that needs
        # a timezone and the public-holiday calendar the syntax can refer to.
        hours = "Mo-Fr 07:00-19:00; Sa-Su 08:00-18:00"

        assert mapped(opening_hours=hours)["opening_hours"] == hours

    def test_whitespace_is_collapsed(self) -> None:
        assert mapped(opening_hours="  Mo-Fr   07:00-19:00 ")["opening_hours"] == (
            "Mo-Fr 07:00-19:00"
        )

    def test_an_absent_tag_is_none(self) -> None:
        assert mapped()["opening_hours"] is None

    def test_a_blank_tag_is_none_rather_than_an_empty_string(self) -> None:
        assert mapped(opening_hours="   ")["opening_hours"] is None


class TestIdentifiers:
    def test_a_node_and_a_way_of_the_same_number_are_two_records(self) -> None:
        """An OSM id is only unique within its element type.

        So the type has to be part of the identifier, or one of the two silently
        wins the collision.
        """
        node = element()
        way = {
            "type": "way",
            "id": 1,
            "center": {"lat": 40.73, "lon": -73.99},
            "tags": node["tags"],
        }
        cafes = osm.normalize([node, way, *enough()[1:]])

        assert {cafe["id"] for cafe in cafes} >= {"n1", "w1"}

    def test_no_identifier_contains_a_slash(self) -> None:
        """OSM writes "node/3506087030"; a spot identifier becomes a URL path.

        ``/spots/osm:node/3506087030`` would be two path segments and a 404.
        """
        assert all("/" not in cafe["id"] for cafe in osm.normalize(enough()))

    def test_an_element_that_is_neither_a_node_nor_a_way_is_an_error(self) -> None:
        with pytest.raises(osm.OsmError, match="no usable type and id"):
            osm.normalize([{"type": "relation", "id": 1, "tags": {}}])


class TestRecordsThatCannotBePublished:
    def test_a_cafe_with_no_name_is_dropped(self) -> None:
        # 33 of the city's 3,011 have no name, and the contract requires one.
        nameless = {**element(), "id": 9001}
        del nameless["tags"]["name"]

        assert "n9001" not in {cafe["id"] for cafe in osm.normalize([nameless, *enough()[1:]])}

    def test_a_way_with_no_centre_is_dropped(self) -> None:
        centreless = {"type": "way", "id": 9002, "tags": {"amenity": "cafe", "name": "No Centre"}}

        assert "w9002" not in {cafe["id"] for cafe in osm.normalize([centreless, *enough()[1:]])}

    def test_a_way_is_published_at_its_bounding_box_centre(self) -> None:
        # `out center` rather than the outline: the rest of the snapshot is
        # building centroids, so a polygon would be a precision nothing else
        # here has.
        way = {
            "type": "way",
            "id": 9003,
            "center": {"lat": 40.7678275, "lon": -74.2810452},
            "tags": {"amenity": "cafe", "name": "Savanna Café"},
        }
        cafes = osm.normalize([way, *enough()[1:]])
        published = next(cafe for cafe in cafes if cafe["id"] == "w9003")

        assert (published["latitude"], published["longitude"]) == (40.7678275, -74.2810452)

    def test_coordinates_are_left_unrounded(self) -> None:
        # ingest.py rounds every coordinate it publishes to six places, and
        # rounding twice in two modules is how the two stop agreeing.
        records = enough()
        records[0] = {**records[0], "lat": 40.7678275}
        published = next(cafe for cafe in osm.normalize(records) if cafe["id"] == "n1")

        assert published["latitude"] == 40.7678275


class TestItRefusesAPartialResult:
    """Failing loudly beats publishing a snapshot missing most of its cafes.

    The committed file is still there, so a build that uses yesterday's cafes is
    better than one that silently drops two thousand of them.
    """

    def test_a_handful_of_records_is_an_error(self) -> None:
        with pytest.raises(osm.OsmError, match="fewer than"):
            osm.normalize([element()])

    def test_an_empty_result_is_an_error(self) -> None:
        with pytest.raises(osm.OsmError, match="fewer than"):
            osm.normalize([])

    def test_the_floor_is_below_what_the_city_actually_has(self) -> None:
        # 3,011 today. A ceiling would be the wrong shape of guard here: the
        # risk is a truncated answer, not an unbounded one.
        assert osm.MINIMUM_CAFES < 3011


class TestTheQuery:
    def test_it_asks_for_the_whole_city(self) -> None:
        query = osm.overpass_query()

        assert '["amenity"="cafe"]' in query
        for value in osm.NYC_BBOX:
            assert str(value) in query

    def test_it_asks_for_nodes_and_ways(self) -> None:
        # A cafe large enough to be a building is a way: 131 of 3,011.
        query = osm.overpass_query()

        assert "node[" in query
        assert "way[" in query

    def test_the_server_is_given_longer_than_the_client_waits(self) -> None:
        # The other way round and the client gives up while the server is still
        # working, which leaves the work done and nobody holding the answer.
        assert osm.QUERY_TIMEOUT_SECONDS < osm.HTTP_TIMEOUT_SECONDS

    def test_the_bounding_box_is_the_importers_own_box_reordered(self) -> None:
        """Overpass orders a bounding box differently from ``NYC_BOUNDS``.

        Two definitions of where New York is have drifted apart on this project
        before, so this asserts they are the same box rather than trusting a
        comment to keep them that way. The constant cannot simply be shared:
        ``ingest`` imports nothing from here and this module importing
        ``ingest`` would be a cycle.
        """
        import ingest

        south, north, west, east = ingest.NYC_BOUNDS

        assert (south, west, north, east) == osm.NYC_BBOX


class TestFetchFailsLoudly:
    """Overpass is free infrastructure and says no in several ways.

    Every one of them has to be an error rather than an empty list, because an
    empty list looks exactly like a city with no coffee shops.
    """

    def stub(self, monkeypatch: pytest.MonkeyPatch, error: Exception) -> None:
        def refuse(*args: Any, **kwargs: Any) -> None:
            raise error

        monkeypatch.setattr(osm.urllib.request, "urlopen", refuse)

    def test_being_rate_limited_says_to_wait_rather_than_to_change_the_query(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self.stub(
            monkeypatch,
            urllib.error.HTTPError(osm.OVERPASS_URL, 429, "Too Many Requests", {}, None),  # type: ignore[arg-type]
        )

        with pytest.raises(osm.OsmError, match="busy rather than"):
            osm.fetch()

    def test_a_gateway_timeout_is_the_same_answer(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Overpass gives up mid-query under load and returns 504. The answer is
        # to wait, not to rewrite the query.
        self.stub(
            monkeypatch,
            urllib.error.HTTPError(osm.OVERPASS_URL, 504, "Gateway Timeout", {}, None),  # type: ignore[arg-type]
        )

        with pytest.raises(osm.OsmError, match="busy rather than"):
            osm.fetch()

    def test_an_unreachable_server_is_an_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.stub(monkeypatch, urllib.error.URLError("no route to host"))

        with pytest.raises(osm.OsmError, match="Could not reach"):
            osm.fetch()

    def test_an_html_error_page_with_a_200_is_an_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Overpass reports a syntax error in the query as HTML with a 200.

        Which is a bug here rather than a server fault, and would otherwise be
        a JSONDecodeError escaping from a module whose errors are all OsmError.
        """

        class Response(io.BytesIO):
            def __enter__(self) -> Response:
                return self

            def __exit__(self, *args: Any) -> None:
                return None

        monkeypatch.setattr(
            osm.urllib.request,
            "urlopen",
            lambda *args, **kwargs: Response(b"<html>syntax error</html>"),
        )

        with pytest.raises(osm.OsmError, match="did not answer with JSON"):
            osm.fetch()

    def test_an_answer_without_an_elements_array_is_an_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class Response(io.BytesIO):
            def __enter__(self) -> Response:
                return self

            def __exit__(self, *args: Any) -> None:
                return None

        monkeypatch.setattr(
            osm.urllib.request,
            "urlopen",
            lambda *args, **kwargs: Response(json.dumps({"version": 0.6}).encode()),
        )

        with pytest.raises(osm.OsmError, match="without an elements array"):
            osm.fetch()


class TestTheCommittedFile:
    """What ``just ingest-osm`` last wrote, which is what the importer reads."""

    @pytest.fixture(scope="class")
    @staticmethod
    def cafes() -> list[dict[str, Any]]:
        path = Path(__file__).resolve().parent / "osm_cafes.json"
        return json.loads(path.read_text("utf-8"))

    def test_it_holds_the_cafes_the_city_has(self, cafes: list[dict[str, Any]]) -> None:
        assert len(cafes) >= osm.MINIMUM_CAFES

    def test_it_is_sorted_and_unique_by_identifier(self, cafes: list[dict[str, Any]]) -> None:
        # Sorted so that an unchanged upstream produces a byte-identical file
        # and the diff shows what actually moved.
        identifiers = [cafe["id"] for cafe in cafes]

        assert identifiers == sorted(identifiers)
        assert len(set(identifiers)) == len(identifiers)

    def test_every_record_has_a_name_and_a_point(self, cafes: list[dict[str, Any]]) -> None:
        for cafe in cafes:
            assert cafe["name"].strip() == cafe["name"] and cafe["name"]
            assert isinstance(cafe["latitude"], float)
            assert isinstance(cafe["longitude"], float)

    def test_it_holds_the_cafe_dohmh_files_as_italian(self, cafes: list[dict[str, Any]]) -> None:
        """Caffe Reggio, which is the reason this source exists.

        Open on MacDougal Street since 1927. DOHMH records its cuisine as
        Italian, so the Coffee/Tea filter loses it, and it went missing from the
        live site when the cafe category moved onto DOHMH.
        """
        reggio = next(cafe for cafe in cafes if cafe["name"] == "Caffe Reggio")

        assert reggio["house_number"] == "119"
        assert reggio["street"] == "MacDougal Street"

    def test_delis_are_not_in_it(self, cafes: list[dict[str, Any]]) -> None:
        """The reason a name match was rejected and this source was not.

        Matching cafe words in a business name pulls in every deli called "Cafe
        Metro". OSM does not have that problem because it tags a deli as
        ``shop=deli``, so almost nothing here reads as one -- and the handful
        that do are places that call themselves a cafe, not a classification
        this importer made.
        """
        delis = [
            cafe
            for cafe in cafes
            if any(word in cafe["name"].lower() for word in ("deli", "bodega", "grocery"))
        ]

        assert len(delis) < len(cafes) * 0.01

    def test_the_three_states_all_occur(self, cafes: list[dict[str, Any]]) -> None:
        # If `false` never occurred the field would be a presence flag, and the
        # three-state handling downstream would be ceremony.
        for field in ("indoor_seating", "venue_wifi"):
            values = {cafe[field] for cafe in cafes}
            assert values == {True, False, None}, field
