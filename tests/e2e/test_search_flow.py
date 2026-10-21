"""End-to-end tests against a running StudySpot.

Everything else in this repository tests a part in isolation: the backend suite
runs Django against a test database, the frontend suite runs components against
a mocked ``fetch``, and the data suite runs the importer against committed
fixtures. None of them would notice if CloudFront routed ``/api/*`` to the wrong
place, if a migration had not been applied, or if the deployed snapshot were
empty -- each failure sits in the seams between the parts rather than inside
one.

These tests drive a real deployment over HTTP instead. Set the base URL:

    STUDYSPOT_E2E_URL=https://d1ulyrfyi06kwp.cloudfront.net just test-e2e

They are skipped without it, because a test suite that silently needs a running
server is worse than one that says so. Any reachable deployment works: the
local ``just start`` stack at http://localhost:7500 as readily as the deployed
site.

The assertions are invariants rather than counts. ``data/spots.json`` is
regenerated whenever the upstream data changes, so a test pinned to "48 spots in
the Bronx" would fail on a perfectly good snapshot. What must hold regardless is
that a borough filter returns only that borough, that the facet counts add up to
the result they describe, and that paging neither repeats a row nor skips one.

Nothing here writes: the API exposes no mutation, and these are all GETs.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

import pytest

BASE_URL = os.environ.get("STUDYSPOT_E2E_URL", "").rstrip("/")

pytestmark = pytest.mark.skipif(
    not BASE_URL,
    reason="Set STUDYSPOT_E2E_URL to the base URL of a running StudySpot.",
)

#: Long enough for a Lambda cold start, which is the slowest thing that can
#: legitimately happen on a first request.
TIMEOUT_SECONDS = 30


def get(path: str, **parameters: Any) -> Any:
    """GET a JSON document from the deployment under test."""
    query = urllib.parse.urlencode({k: v for k, v in parameters.items() if v is not None})
    url = f"{BASE_URL}/api{path}" + (f"?{query}" if query else "")

    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        # The API reports its own errors in a JSON envelope, and a test that
        # prints that is far more useful than one that prints "HTTP 422".
        pytest.fail(f"GET {url} -> {error.code}: {error.read().decode(errors='replace')[:400]}")


@pytest.fixture(scope="session")
def any_spot() -> dict[str, Any]:
    """One real spot from the deployment, to drive the lookups that need an id."""
    page = get("/spots", limit=1)
    if not page["items"]:
        pytest.skip("The deployed database is empty; run `just aws-load` first.")
    return page["items"][0]


class TestTheDeploymentIsWiredUp:
    """The seams the unit suites cannot see."""

    def test_liveness_answers(self) -> None:
        assert get("/health/live") == {"status": "ok"}

    def test_the_api_is_reachable_under_the_public_prefix(self) -> None:
        # CloudFront strips /api before Django sees the request. If that rewrite
        # were wrong, this would return the frontend's HTML rather than JSON.
        assert "pagination" in get("/spots", limit=1)

    def test_the_database_has_been_loaded(self) -> None:
        # An unloaded deployment answers 200 with an empty page, which is a
        # valid state and not a working one.
        assert get("/spots", limit=1)["pagination"]["total"] > 0

    def test_the_migrations_have_been_applied(self) -> None:
        # Searching touches the generated tsvector column and the trigram
        # indexes. On a deployment missing a migration this is a 500, not a 0.
        assert "items" in get("/spots/search", q="library", limit=1)


class TestSearchingTheWayPeopleDo:
    def test_a_name_finds_its_place(self) -> None:
        results = get("/spots/search", q="library", limit=5)["items"]
        assert results
        assert any("librar" in spot["name"].lower() for spot in results)

    def test_a_misspelling_still_finds_something(self) -> None:
        # The trigram fallback. Full text cannot match a word Postgres has
        # never indexed, so this is the pass that has to catch it.
        assert get("/spots/search", q="libary", limit=1)["pagination"]["total"] > 0

    def test_every_word_has_to_match(self) -> None:
        # The precision the full-text pass exists for: adding a word narrows.
        broad = get("/spots/search", q="library", limit=1)["pagination"]["total"]
        narrow = get("/spots/search", q="library bobst", limit=1)["pagination"]["total"]
        assert 0 < narrow < broad

    def test_word_order_does_not_matter(self) -> None:
        one = get("/spots/search", q="library bobst", limit=5)
        other = get("/spots/search", q="bobst library", limit=5)
        assert [spot["id"] for spot in one["items"]] == [spot["id"] for spot in other["items"]]

    def test_an_unrelated_query_returns_nothing(self) -> None:
        # Rather than everything in an arbitrary order, which is what a ranked
        # search with no threshold does.
        assert get("/spots/search", q="helicopter", limit=1)["pagination"]["total"] == 0

    def test_a_prefix_works_for_search_as_you_type(self) -> None:
        # What the browser sends on a debounced keystroke, before the word is
        # finished.
        assert get("/spots/search", q="bob", limit=1)["pagination"]["total"] > 0


class TestFilteringNarrows:
    def test_a_borough_filter_returns_only_that_borough(self) -> None:
        page = get("/spots", borough="Bronx", limit=100)
        assert page["items"]
        assert {spot["borough"] for spot in page["items"]} == {"Bronx"}

    def test_a_filter_narrows_rather_than_widens(self) -> None:
        everything = get("/spots", limit=1)["pagination"]["total"]
        bronx = get("/spots", borough="Bronx", limit=1)["pagination"]["total"]
        assert 0 < bronx < everything

    def test_filters_combine_with_and(self) -> None:
        bronx = get("/spots", borough="Bronx", limit=1)["pagination"]["total"]
        both = get("/spots", borough="Bronx", free_public_wifi="true", limit=1)
        assert both["pagination"]["total"] <= bronx

    def test_a_filter_applies_to_search_too(self) -> None:
        page = get("/spots/search", q="library", borough="Bronx", limit=100)
        assert page["items"]
        assert {spot["borough"] for spot in page["items"]} == {"Bronx"}

    def test_a_blank_filter_is_rejected_rather_than_ignored(self) -> None:
        # A filter whose value was lost should fail, not quietly widen the
        # search. urlopen raises on 4xx, so this asserts the status directly.
        request = urllib.request.Request(f"{BASE_URL}/api/spots?borough=")
        with pytest.raises(urllib.error.HTTPError) as raised:
            urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS)
        assert raised.value.code == 422


class TestTheFacetsDescribeTheResults:
    def test_borough_counts_add_up_to_the_total(self) -> None:
        # Borough is never null, so its facet partitions the result set exactly.
        # If the counts were taken over the whole table rather than the current
        # results, this would overshoot.
        facets = get("/spots/facets", borough=None)
        total = get("/spots", limit=1)["pagination"]["total"]
        assert sum(row["count"] for row in facets["boroughs"]) == total

    def test_they_follow_a_search(self) -> None:
        facets = get("/spots/facets", q="library")
        total = get("/spots/search", q="library", limit=1)["pagination"]["total"]
        assert sum(row["count"] for row in facets["boroughs"]) == total

    def test_they_follow_a_filter(self) -> None:
        facets = get("/spots/facets", borough="Bronx")
        total = get("/spots", borough="Bronx", limit=1)["pagination"]["total"]
        # The borough facet keeps its own filter out, so check one that narrows.
        assert sum(row["count"] for row in facets["categories"]) == total

    def test_a_facet_keeps_its_own_filter_out(self) -> None:
        # Otherwise the chosen value would be the only one offered and there
        # would be no way back to the others.
        unfiltered = {row["value"] for row in get("/spots/facets")["boroughs"]}
        filtered = {row["value"] for row in get("/spots/facets", borough="Bronx")["boroughs"]}
        assert filtered == unfiltered

    def test_every_offered_value_actually_returns_something(self) -> None:
        # The promise a count makes. Taken over the whole table instead, a
        # category offered under a borough that has none returns an empty page.
        facets = get("/spots/facets", borough="Bronx")
        for row in facets["categories"]:
            page = get("/spots", borough="Bronx", category=row["value"], limit=1)
            assert page["pagination"]["total"] == row["count"], row["value"]


class TestPagingIsStable:
    def test_a_page_reports_where_it_sits(self) -> None:
        page = get("/spots", limit=5)
        assert page["pagination"]["count"] == len(page["items"]) == 5
        assert page["pagination"]["has_more"] is True

    def test_paging_neither_repeats_nor_skips(self) -> None:
        # The property the (name, id) ordering exists for.
        seen: list[str] = []
        for offset in range(0, 60, 20):
            seen.extend(spot["id"] for spot in get("/spots", limit=20, offset=offset)["items"])
        assert len(seen) == len(set(seen))


class TestOneSpot:
    def test_a_spot_can_be_fetched_by_its_identifier(self, any_spot: dict[str, Any]) -> None:
        # The colon in "facdb:a1b2c3" has to survive CloudFront, API Gateway and
        # Django's URL routing, which is three chances to be mangled.
        assert get(f"/spots/{any_spot['id']}")["id"] == any_spot["id"]

    def test_it_carries_the_published_contract(self, any_spot: dict[str, Any]) -> None:
        assert set(any_spot) == {
            "id",
            "name",
            "category",
            "address",
            "neighborhood",
            "borough",
            "latitude",
            "longitude",
            "university",
            "operator",
            "free_public_wifi",
            "no_purchase_needed",
            "subway_station",
            "subway_routes",
            "subway_metres",
            "subway_step_free",
            "nearby_spots",
            "outdoor_seating",
            "indoor_seating",
            "venue_wifi",
            "opening_hours",
        }

    def test_an_unknown_identifier_is_a_404(self) -> None:
        request = urllib.request.Request(f"{BASE_URL}/api/spots/facdb:nothing")
        with pytest.raises(urllib.error.HTTPError) as raised:
            urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS)
        assert raised.value.code == 404


class TestTheDetailPagesAreServed:
    """Every spot has a prerendered page, written as real HTML at build time.

    The identifier carries a colon -- "facdb:a1b2c3" -- which has to survive
    being an S3 key, a CloudFront path, and the edge function that appends
    .html to a segment without a dot. None of that is exercised by a unit test.
    """

    def page(self, path: str) -> tuple[int, str]:
        request = urllib.request.Request(f"{BASE_URL}{path}")
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                return response.status, response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as error:
            return error.code, ""

    def test_a_spot_has_its_own_page(self, any_spot: dict[str, Any]) -> None:
        status, body = self.page(f"/spots/{any_spot['id']}")

        assert status == 200
        # Prerendered, so the name is in the HTML rather than fetched after.
        assert any_spot["name"].split(" (")[0][:20] in body

    def test_the_identifier_keeps_its_colon(self, any_spot: dict[str, Any]) -> None:
        assert ":" in any_spot["id"], "the fixture should use a prefixed identifier"
        assert self.page(f"/spots/{any_spot['id']}")[0] == 200

    def test_an_unknown_spot_has_no_page(self) -> None:
        # No page was built for it, so S3 has no key and the 403 mapping turns
        # that into the application's 404.
        assert self.page("/spots/facdb:nothing")[0] == 404


class TestTheBrowserAppIsServed:
    def test_the_site_responds(self) -> None:
        request = urllib.request.Request(BASE_URL + "/")
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            assert response.status == 200
            assert "text/html" in response.headers.get("content-type", "")

    def test_a_missing_path_is_a_404_rather_than_the_homepage(self) -> None:
        # The adapter's fallback is 404.html precisely so that a mistyped URL
        # does not serve the homepage under the wrong address.
        request = urllib.request.Request(f"{BASE_URL}/no-such-page")
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                status = response.status
        except urllib.error.HTTPError as error:
            status = error.code
        assert status == 404
