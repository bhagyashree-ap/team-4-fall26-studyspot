"""Contract tests for ``GET /spots/facets``.

The counts beside a filter control are promises about what picking that value
returns. Counted over the whole table they stop being true the moment any other
filter is on, which is the behaviour these tests pin down: every facet reflects
the request already in force, except for its own filter.
"""

from __future__ import annotations

from typing import Any

import pytest

from spots.models import StudySpot

#: Three boroughs, four categories, three campuses and a mix of Wi-Fi, chosen so
#: that every filter changes some other facet's counts.
RECORDS: list[dict[str, Any]] = [
    {
        "id": "facdb:bobst",
        "name": "Bobst Library",
        "category": "academic_library",
        "no_purchase_needed": True,
        "address": None,
        "neighborhood": "Greenwich Village",
        "borough": "Manhattan",
        "latitude": 40.7295,
        "longitude": -73.9973,
        "university": "New York University",
        "free_public_wifi": True,
    },
    {
        "id": "facdb:butler",
        "name": "Butler Library",
        "category": "academic_library",
        "no_purchase_needed": True,
        "address": None,
        "neighborhood": "Morningside Heights",
        "borough": "Manhattan",
        "latitude": 40.8063,
        "longitude": -73.9634,
        "university": "Columbia University",
        "free_public_wifi": False,
    },
    {
        "id": "facdb:125th",
        "name": "125th Street Library",
        "category": "public_library",
        "no_purchase_needed": True,
        "address": None,
        "neighborhood": "East Harlem (North)",
        "borough": "Manhattan",
        "latitude": 40.803,
        "longitude": -73.9348,
        "university": None,
        "free_public_wifi": True,
    },
    {
        "id": "facdb:allerton",
        "name": "Allerton Library",
        "category": "public_library",
        "no_purchase_needed": True,
        "address": None,
        "neighborhood": None,
        "borough": "Bronx",
        "latitude": 40.8668,
        "longitude": -73.8632,
        "university": None,
        "free_public_wifi": False,
    },
    {
        "id": "facdb:fordham",
        "name": "Fordham University Rose Hill",
        "category": "university_building",
        "no_purchase_needed": True,
        "address": None,
        "neighborhood": "Belmont",
        "borough": "Bronx",
        "latitude": 40.8614,
        "longitude": -73.8857,
        "university": "Fordham University",
        "free_public_wifi": True,
    },
    {
        "id": "dohmh:hundred",
        "name": "100% Coffee",
        "category": "cafe",
        "no_purchase_needed": False,
        "address": None,
        "neighborhood": "Greenpoint",
        "borough": "Brooklyn",
        "latitude": 40.7304,
        "longitude": -73.9543,
        "university": None,
        "free_public_wifi": False,
    },
]


@pytest.fixture
def spots(db: None) -> list[StudySpot]:
    return StudySpot.objects.bulk_create(StudySpot(**record) for record in RECORDS)


def counts(facet: list[dict[str, Any]]) -> dict[str, int]:
    """A facet list as a value-to-count mapping, for readable assertions."""
    return {row["value"]: row["count"] for row in facet}


class TestEnvelope:
    def test_reports_every_facet(self, client: Any, spots: list[StudySpot]) -> None:
        body = client.get("/spots/facets").json()
        assert set(body) == {
            "boroughs",
            "categories",
            "universities",
            "free_public_wifi",
            "no_purchase_needed",
            "indoor_seating",
        }

    def test_a_value_list_carries_a_value_and_a_count(
        self, client: Any, spots: list[StudySpot]
    ) -> None:
        assert set(client.get("/spots/facets").json()["boroughs"][0]) == {"value", "count"}

    def test_wifi_is_a_single_count(self, client: Any, spots: list[StudySpot]) -> None:
        # A boolean has no list of values to offer: the control is a checkbox,
        # so the only useful number is how many spots remain when it is ticked.
        assert client.get("/spots/facets").json()["free_public_wifi"] == 3

    def test_cost_is_a_single_count(self, client: Any, spots: list[StudySpot]) -> None:
        # Five of the six fixture records cost nothing to sit in; the cafe is
        # the one that expects a purchase.
        assert client.get("/spots/facets").json()["no_purchase_needed"] == 5

    def test_counts_are_ordered_by_size(self, client: Any, spots: list[StudySpot]) -> None:
        sizes = [row["count"] for row in client.get("/spots/facets").json()["boroughs"]]
        assert sizes == sorted(sizes, reverse=True)


class TestWithoutFilters:
    def test_describes_the_whole_table(self, client: Any, spots: list[StudySpot]) -> None:
        body = client.get("/spots/facets").json()
        assert counts(body["boroughs"]) == {"Manhattan": 3, "Bronx": 2, "Brooklyn": 1}
        assert counts(body["categories"]) == {
            "academic_library": 2,
            "public_library": 2,
            "cafe": 1,
            "university_building": 1,
        }

    def test_a_null_column_is_not_a_facet_value(self, client: Any, spots: list[StudySpot]) -> None:
        # Three of the six records have no campus. "No campus" is not a value a
        # filter can be set to, so it is absent rather than counted as null.
        assert counts(client.get("/spots/facets").json()["universities"]) == {
            "New York University": 1,
            "Columbia University": 1,
            "Fordham University": 1,
        }


class TestFiltersNarrowOtherFacets:
    def test_a_borough_narrows_the_categories(self, client: Any, spots: list[StudySpot]) -> None:
        body = client.get("/spots/facets?borough=Manhattan").json()
        assert counts(body["categories"]) == {"academic_library": 2, "public_library": 1}

    def test_a_value_that_now_matches_nothing_is_not_offered(
        self, client: Any, spots: list[StudySpot]
    ) -> None:
        # The whole point. Manhattan has no cafe and no university, so offering
        # either would be offering a filter that returns an empty page.
        body = client.get("/spots/facets?borough=Manhattan").json()
        assert "cafe" not in counts(body["categories"])
        assert "university_building" not in counts(body["categories"])

    def test_a_borough_narrows_the_campuses(self, client: Any, spots: list[StudySpot]) -> None:
        body = client.get("/spots/facets?borough=Bronx").json()
        assert counts(body["universities"]) == {"Fordham University": 1}

    def test_a_borough_narrows_the_wifi_count(self, client: Any, spots: list[StudySpot]) -> None:
        assert client.get("/spots/facets?borough=Manhattan").json()["free_public_wifi"] == 2
        assert client.get("/spots/facets?borough=Bronx").json()["free_public_wifi"] == 1

    def test_wifi_narrows_the_other_facets(self, client: Any, spots: list[StudySpot]) -> None:
        body = client.get("/spots/facets?free_public_wifi=true").json()
        assert counts(body["boroughs"]) == {"Manhattan": 2, "Bronx": 1}

    def test_filters_combine(self, client: Any, spots: list[StudySpot]) -> None:
        body = client.get("/spots/facets?borough=Manhattan&free_public_wifi=true").json()
        assert counts(body["categories"]) == {"academic_library": 1, "public_library": 1}

    def test_a_name_filter_narrows_them_too(self, client: Any, spots: list[StudySpot]) -> None:
        body = client.get("/spots/facets?name=library").json()
        assert counts(body["boroughs"]) == {"Manhattan": 3, "Bronx": 1}


class TestAFacetIgnoresItsOwnFilter:
    """Otherwise a chosen filter leaves no way back to the other values."""

    def test_a_borough_filter_leaves_every_borough_offered(
        self, client: Any, spots: list[StudySpot]
    ) -> None:
        body = client.get("/spots/facets?borough=Manhattan").json()
        assert counts(body["boroughs"]) == {"Manhattan": 3, "Bronx": 2, "Brooklyn": 1}

    def test_a_category_filter_leaves_every_category_offered(
        self, client: Any, spots: list[StudySpot]
    ) -> None:
        body = client.get("/spots/facets?category=library").json()
        assert set(counts(body["categories"])) == {
            "academic_library",
            "public_library",
            "cafe",
            "university_building",
        }

    def test_the_wifi_count_ignores_the_wifi_filter(
        self, client: Any, spots: list[StudySpot]
    ) -> None:
        # Ticked or not, the number means the same thing: how many spots have
        # Wi-Fi under the *other* filters.
        assert client.get("/spots/facets?free_public_wifi=true").json()["free_public_wifi"] == 3
        assert client.get("/spots/facets?free_public_wifi=false").json()["free_public_wifi"] == 3

    def test_a_category_filter_still_narrows_the_boroughs(
        self, client: Any, spots: list[StudySpot]
    ) -> None:
        # Its own facet is spared; everything else is not.
        body = client.get("/spots/facets?category=academic_library").json()
        assert counts(body["boroughs"]) == {"Manhattan": 2}


class TestWithAQuery:
    def test_a_query_narrows_the_facets(self, client: Any, spots: list[StudySpot]) -> None:
        body = client.get("/spots/facets?q=library").json()
        assert "cafe" not in counts(body["categories"])

    def test_the_counts_add_up_to_what_the_search_returns(
        self, client: Any, spots: list[StudySpot]
    ) -> None:
        # Borough is never null, so its facet partitions the result set exactly.
        facets = client.get("/spots/facets?q=library").json()
        total = client.get("/spots/search?q=library&limit=1").json()["pagination"]["total"]
        assert sum(row["count"] for row in facets["boroughs"]) == total

    def test_each_value_is_grouped_once(self, client: Any, spots: list[StudySpot]) -> None:
        # Guards the aggregation itself: the ranked queryset carries a relevance
        # annotation and an ordering, and letting either reach the GROUP BY puts
        # every row in a group of its own -- "Manhattan: 1" three times over.
        values = [row["value"] for row in client.get("/spots/facets?q=library").json()["boroughs"]]
        assert len(values) == len(set(values))

    def test_a_query_combines_with_a_filter(self, client: Any, spots: list[StudySpot]) -> None:
        body = client.get("/spots/facets?q=library&borough=Manhattan").json()
        assert counts(body["categories"]) == {"academic_library": 2, "public_library": 1}

    def test_a_query_matching_nothing_empties_every_facet(
        self, client: Any, spots: list[StudySpot]
    ) -> None:
        body = client.get("/spots/facets?q=zzzzzzzz").json()
        assert body["boroughs"] == []
        assert body["categories"] == []
        assert body["universities"] == []
        assert body["free_public_wifi"] == 0


class TestValidation:
    def test_an_unknown_parameter_is_rejected(self, client: Any, spots: list[StudySpot]) -> None:
        response = client.get("/spots/facets?neighbourhood=Greenpoint")
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"

    @pytest.mark.parametrize("query", ["q=", "borough=", "category="])
    def test_a_blank_parameter_is_rejected(
        self, client: Any, spots: list[StudySpot], query: str
    ) -> None:
        assert client.get(f"/spots/facets?{query}").status_code == 422

    def test_an_unknown_borough_is_rejected(self, client: Any, spots: list[StudySpot]) -> None:
        assert client.get("/spots/facets?borough=Yonkers").status_code == 422

    @pytest.mark.parametrize("query", ["limit=5", "offset=5"])
    def test_paging_parameters_are_rejected(
        self, client: Any, spots: list[StudySpot], query: str
    ) -> None:
        # A facet list is as long as the number of distinct values. Paging it
        # would mean a control that offers some of the values.
        assert client.get(f"/spots/facets?{query}").status_code == 422


class TestTheCostFacet:
    """ "Can I work here without buying something?" is not any one category.

    It is true of every library and of the campus buildings, and false only of
    cafes, so the count cannot be read off the category list.
    """

    def test_it_narrows_with_the_other_filters(self, client: Any, spots: list[StudySpot]) -> None:
        # Manhattan holds two academic libraries and one public library, all
        # free, and no cafe.
        assert client.get("/spots/facets?borough=Manhattan").json()["no_purchase_needed"] == 3
        assert client.get("/spots/facets?borough=Brooklyn").json()["no_purchase_needed"] == 0

    def test_it_ignores_its_own_filter(self, client: Any, spots: list[StudySpot]) -> None:
        # Ticked or not, it means the same thing: how many of the spots the
        # other filters leave cost nothing.
        for value in ("true", "false"):
            body = client.get(f"/spots/facets?no_purchase_needed={value}").json()
            assert body["no_purchase_needed"] == 5

    def test_it_narrows_the_other_facets(self, client: Any, spots: list[StudySpot]) -> None:
        body = client.get("/spots/facets?no_purchase_needed=true").json()
        assert "cafe" not in counts(body["categories"])

    def test_the_inverse_leaves_only_the_cafes(self, client: Any, spots: list[StudySpot]) -> None:
        body = client.get("/spots/facets?no_purchase_needed=false").json()
        assert counts(body["categories"]) == {"cafe": 1}
