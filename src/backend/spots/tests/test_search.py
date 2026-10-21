"""Tests for the ranked search endpoint.

``GET /spots`` filters and ``GET /spots/search`` ranks, and the difference is
the point: a filter answers "does this match", a search answers "which of these
is closest". The cases below are the ones a filter gets wrong -- a misspelling,
an initialism, a fragment of a long title -- plus the one a ranked search gets
wrong if the threshold is too low, which is returning everything.
"""

from __future__ import annotations

from typing import Any

import pytest

from spots.models import StudySpot
from spots.search import INITIALISMS, THRESHOLD, expand, is_plain, partial, precise, search

pytestmark = pytest.mark.django_db

#: Chosen so that every ranking rule has something to act on: a long title whose
#: distinctive word sits in the middle, two names sharing a word, a neighborhood
#: that is not in any name, and an accented name.
RECORDS: list[dict[str, Any]] = [
    {
        "id": "nyu:bobst",
        "name": "Elmer Holmes Bobst Library",
        "category": "academic_library",
        "no_purchase_needed": True,
        "address": "70 Washington Square S",
        "neighborhood": "Greenwich Village",
        "borough": "Manhattan",
        "latitude": 40.7295,
        "longitude": -73.9973,
        "university": "New York University",
    },
    {
        "id": "nyu:kimmel",
        "name": "Kimmel Center for University Life",
        "category": "university_building",
        "no_purchase_needed": True,
        "address": "60 Washington Square S",
        "neighborhood": "Greenwich Village",
        "borough": "Manhattan",
        "latitude": 40.7301,
        "longitude": -73.9977,
        "university": "New York University",
    },
    {
        "id": "facdb:nypl-53",
        "name": "53rd Street Library",
        "category": "public_library",
        "no_purchase_needed": True,
        "operator": "New York Public Library",
        "address": "18 West 53 Street",
        "neighborhood": "Midtown-Times Square",
        "borough": "Manhattan",
        "latitude": 40.7606,
        "longitude": -73.9787,
        "university": None,
    },
    {
        "id": "facdb:baychester",
        "name": "Baychester Library",
        "category": "public_library",
        "no_purchase_needed": True,
        "address": "2049 Asch Loop North",
        "neighborhood": "Co-op City",
        "borough": "Bronx",
        "latitude": 40.8714,
        "longitude": -73.8278,
        "university": None,
    },
    {
        # Its campus says CUNY; nothing anywhere says "City University of New
        # York", which is what the initialism expands to.
        "id": "facdb:newman",
        "name": "Newman Library",
        "category": "academic_library",
        "no_purchase_needed": True,
        "address": "151 East 25 Street",
        "neighborhood": "Gramercy",
        "borough": "Manhattan",
        "latitude": 40.7399,
        "longitude": -73.9829,
        "university": "CUNY Bernard M. Baruch College",
    },
    {
        "id": "dohmh:grumpy",
        "name": "Café Grumpy",
        "category": "cafe",
        "no_purchase_needed": False,
        "address": None,
        "neighborhood": "Chelsea",
        "borough": "Manhattan",
        "latitude": 40.7442,
        "longitude": -74.0,
        "university": None,
    },
]


@pytest.fixture
def spots() -> list[StudySpot]:
    return StudySpot.objects.bulk_create(StudySpot(**record) for record in RECORDS)


def names(query: str) -> list[str]:
    return [spot.name for spot in search(query)]


class TestTypos:
    """The failure that motivated the endpoint: a filter returns nothing."""

    @pytest.mark.parametrize(
        ("typo", "expected"),
        [
            ("libary", "53rd Street Library"),
            ("kimel", "Kimmel Center for University Life"),
            ("bobts", "Elmer Holmes Bobst Library"),
            ("baychestr", "Baychester Library"),
        ],
    )
    def test_a_misspelling_still_finds_the_place(
        self, spots: list[StudySpot], typo: str, expected: str
    ) -> None:
        assert expected in names(typo)

    def test_the_best_match_comes_first(self, spots: list[StudySpot]) -> None:
        assert names("kimel")[0] == "Kimmel Center for University Life"


class TestShortenedNames:
    def test_a_fragment_of_a_long_title_matches(self, spots: list[StudySpot]) -> None:
        # "Bobst" is the fourth word of its title; a prefix match would miss it.
        assert names("bobst")[0] == "Elmer Holmes Bobst Library"

    def test_an_initialism_is_expanded(self, spots: list[StudySpot]) -> None:
        # No fuzzy algorithm connects NYPL to its expansion: they share almost
        # no trigrams. The lookup is why this works.
        assert expand("NYPL") == '"New York Public Library"'
        assert expand("nypl") == expand("NYPL")

    def test_an_unknown_word_is_left_alone(self) -> None:
        assert expand("bobst") == "bobst"

    def test_every_word_is_expanded(self) -> None:
        # This used to expand only a whole-query initialism, because against a
        # single trigram comparison replacing one word of several changed what
        # the rest was measured against. Full text matches word by word, so it
        # can now mean what it says.
        assert expand("nyu library") == '"New York University" library'

    def test_an_initialism_finds_what_it_stands_for(self, spots: list[StudySpot]) -> None:
        assert "Elmer Holmes Bobst Library" in names("nyu library")
        assert "Kimmel Center for University Life" not in names("nyu library")

    def test_every_initialism_is_stored_folded(self) -> None:
        # expand() looks up a casefolded key, so a capitalised one would never
        # be found and the entry would silently do nothing.
        assert all(key == key.casefold() for key in INITIALISMS)


class TestRanking:
    def test_an_exact_name_outranks_a_fuzzy_match(self, spots: list[StudySpot]) -> None:
        assert names("Baychester Library")[0] == "Baychester Library"

    def test_a_name_outranks_a_neighborhood(self, spots: list[StudySpot]) -> None:
        # A place called Greenwich Village would beat places in it; here the
        # neighborhood match should still appear.
        assert "Elmer Holmes Bobst Library" in names("Greenwich Village")

    def test_a_neighborhood_absent_from_every_name_still_matches(
        self, spots: list[StudySpot]
    ) -> None:
        assert names("Co-op City") == ["Baychester Library"]

    def test_an_accented_name_is_found_by_its_accented_spelling(
        self, spots: list[StudySpot]
    ) -> None:
        assert "Café Grumpy" in names("Café")

    def test_results_are_ordered_by_relevance(self, spots: list[StudySpot]) -> None:
        results = list(search("library"))
        relevance = [spot.relevance for spot in results]
        assert relevance == sorted(relevance, reverse=True)


class TestThreshold:
    def test_an_unrelated_query_matches_nothing(self, spots: list[StudySpot]) -> None:
        # The risk a ranked search carries that a filter does not: returning
        # everything, ordered.
        assert names("zzzznowhere") == []

    def test_the_threshold_is_above_what_unrelated_words_score(self) -> None:
        # Unrelated words sit around 0.33 against this data; the margin is what
        # keeps a search from degrading into a listing.
        assert THRESHOLD > 0.33


class TestEndpoint:
    def test_returns_the_published_envelope(self, client: Any, spots: list[StudySpot]) -> None:
        body = client.get("/spots/search?q=library").json()

        assert set(body) == {"items", "pagination"}
        assert set(body["pagination"]) == {"limit", "offset", "count", "total", "has_more"}

    def test_does_not_leak_the_relevance_score(self, client: Any, spots: list[StudySpot]) -> None:
        # It orders the results; publishing it would be a number the contract
        # has to keep stable for no one's benefit.
        body = client.get("/spots/search?q=library").json()
        assert "relevance" not in body["items"][0]

    def test_the_route_is_not_captured_by_the_detail_route(
        self, client: Any, spots: list[StudySpot]
    ) -> None:
        # /spots/<id> would match "search" as an identifier if it were declared
        # first, and the endpoint would 404 forever.
        assert client.get("/spots/search?q=library").status_code == 200

    def test_a_missing_query_is_422(self, client: Any, spots: list[StudySpot]) -> None:
        response = client.get("/spots/search")

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"

    @pytest.mark.parametrize("query", ["q=", "q=library&bogus=1", "q=library&limit=0"])
    def test_a_bad_parameter_is_422(self, client: Any, spots: list[StudySpot], query: str) -> None:
        assert client.get(f"/spots/search?{query}").status_code == 422

    def test_paging_reports_the_total_beyond_the_page(
        self, client: Any, spots: list[StudySpot]
    ) -> None:
        body = client.get("/spots/search?q=library&limit=1").json()

        assert body["pagination"]["count"] == 1
        assert body["pagination"]["total"] > 1
        assert body["pagination"]["has_more"] is True


class TestTheCampusIsSearchable:
    """The gap that motivated the full-text pass.

    Neither of these two names NYU, and both belong to it. Against the name
    alone a search for the university found neither; in the real snapshot that
    was 11 of the 14 spots related to NYU.
    """

    def test_a_campus_finds_buildings_that_do_not_name_it(self, spots: list[StudySpot]) -> None:
        found = names("New York University")

        assert "Elmer Holmes Bobst Library" in found
        assert "Kimmel Center for University Life" in found

    def test_an_initialism_for_it_works_too(self, spots: list[StudySpot]) -> None:
        assert set(names("nyu")) == {
            "Elmer Holmes Bobst Library",
            "Kimmel Center for University Life",
        }

    def test_a_spot_with_no_campus_is_not_dragged_in(self, spots: list[StudySpot]) -> None:
        assert "Baychester Library" not in names("nyu")

    def test_the_name_outranks_the_campus(self, spots: list[StudySpot]) -> None:
        # "University" is in Kimmel's name and only in Bobst's campus, which is
        # the weighting: a word in the name counts for more than the same word
        # in a field the spot merely sits near.
        found = names("university")

        assert found.index("Kimmel Center for University Life") < found.index(
            "Elmer Holmes Bobst Library"
        )


class TestTheAddressIsSearchable:
    def test_an_address_finds_the_spot(self, spots: list[StudySpot]) -> None:
        # Neither name mentions Washington Square; both sit on it.
        assert set(names("Washington Square")) == {
            "Elmer Holmes Bobst Library",
            "Kimmel Center for University Life",
        }

    def test_the_name_outranks_the_address(self, spots: list[StudySpot]) -> None:
        # Address is the lowest weight on purpose: a place *called* X is almost
        # always what was meant, not the places on X Street.
        found = names("53rd Street")

        assert found[0] == "53rd Street Library"


class TestEveryWordHasToMatch:
    """What a single trigram comparison could not do.

    Scoring the query against the best-matching run of words meant "library
    bobst" scored as well against every library as against the one named Bobst.
    In the real snapshot it returned 170 results.
    """

    def test_a_second_word_narrows_instead_of_widening(self, spots: list[StudySpot]) -> None:
        # Order is relevance then name, and all four score the same on one
        # word, so the set is what matters here.
        assert set(names("library")) == {
            "53rd Street Library",
            "Baychester Library",
            "Elmer Holmes Bobst Library",
            "Newman Library",
        }
        assert names("library bobst") == ["Elmer Holmes Bobst Library"]

    def test_word_order_does_not_matter(self, spots: list[StudySpot]) -> None:
        assert names("library bobst") == names("bobst library")

    def test_a_word_that_matches_nothing_rules_the_row_out(self, spots: list[StudySpot]) -> None:
        assert names("bobst brooklyn") == []

    def test_a_quoted_phrase_is_taken_literally(self, spots: list[StudySpot]) -> None:
        # websearch_to_tsquery, so a phrase in quotes has to appear in order.
        assert names('"Washington Square"') != []
        assert names('"Square Washington"') == []

    def test_a_leading_minus_excludes(self, spots: list[StudySpot]) -> None:
        assert set(names("library -bobst")) == {
            "53rd Street Library",
            "Baychester Library",
            "Newman Library",
        }


class TestTheTwoPassesInOrder:
    def test_a_spelled_query_does_not_reach_the_fuzzy_pass(self, spots: list[StudySpot]) -> None:
        # If it did, "library bobst" would come back with every library in it:
        # that is exactly what the trigram pass scores highly.
        assert names("library bobst") == ["Elmer Holmes Bobst Library"]

    def test_a_misspelling_falls_through_to_it(self, spots: list[StudySpot]) -> None:
        # Postgres has never indexed "libary", so full text cannot match it at
        # all and the trigram pass is the only thing that can.
        assert precise("libary", StudySpot.objects.all()).count() == 0
        assert names("libary") != []

    def test_a_query_matching_neither_returns_nothing(self, spots: list[StudySpot]) -> None:
        assert names("helicopter") == []


class TestTheBoroughAndCategoryAreSearchable:
    """Both have a filter of their own, and a search box is where people type
    them first.

    Without them "bronx public library" found three spots in the real snapshot
    and put a Manhattan one first, and "manhattan library" found five of the
    sixty-eight.
    """

    def test_a_borough_finds_what_is_in_it(self, spots: list[StudySpot]) -> None:
        assert names("Bronx") == ["Baychester Library"]

    def test_a_category_finds_its_own_kind(self, spots: list[StudySpot]) -> None:
        # Typed as a person would write it; Postgres splits the underscore in
        # "public_library" itself, so the stored value indexes the same way.
        assert set(names("public library")) == {"53rd Street Library", "Baychester Library"}

    def test_a_borough_and_a_category_together(self, spots: list[StudySpot]) -> None:
        assert names("bronx public library") == ["Baychester Library"]

    def test_a_broad_word_still_cannot_flood_a_narrow_one(self, spots: list[StudySpot]) -> None:
        # The protection against clutter is the AND, not a weight: every
        # academic library matches "library", only one matches "bobst".
        assert names("library bobst") == ["Elmer Holmes Bobst Library"]

    def test_the_name_still_outranks_the_borough(self, spots: list[StudySpot]) -> None:
        # Lowest weight, so a place called Manhattan would beat the places in
        # it. Nothing here is called Bronx, so this checks the weaker claim
        # that a name match leads.
        found = names("Baychester")
        assert found[0] == "Baychester Library"


class TestAnExpansionThatMatchesNothing:
    """The literal term gets a turn before the fuzzy pass does.

    CUNY is the case that proved it: the expansion is "City University of New
    York", which no record contains, so the only attempt failed and the query
    fell through to trigrams -- where "New York Cit..." matched "New York City
    Bagel & Coffee House". Typing CUNY returned bagel shops.
    """

    def test_the_expansion_itself_finds_nothing(self, spots: list[StudySpot]) -> None:
        assert expand("cuny") == '"City University of New York"'
        assert precise("City University of New York", StudySpot.objects.all()).count() == 0

    def test_the_literal_term_finds_the_campus(self, spots: list[StudySpot]) -> None:
        assert names("cuny") == ["Newman Library"]

    def test_an_expansion_that_does_match_is_still_preferred(self, spots: list[StudySpot]) -> None:
        # NYU is the case the expansion exists for: no record is named "NYU",
        # and two carry "New York University" as their campus.
        assert expand("nyu") == '"New York University"'
        assert set(names("nyu")) == {
            "Elmer Holmes Bobst Library",
            "Kimmel Center for University Life",
        }

    def test_a_misspelling_still_reaches_the_fuzzy_pass(self, spots: list[StudySpot]) -> None:
        # Nothing above may break the reason the second pass exists.
        assert "53rd Street Library" in names("libary")


class TestTheOperatorIsSearchable:
    """What makes an acronym for a library system work.

    "53rd Street Library" does not say who runs it, and neither does any other
    branch -- they are named after their neighborhoods. Only the operator does.
    """

    def test_a_system_finds_its_branches(self, spots: list[StudySpot]) -> None:
        assert "53rd Street Library" in names("New York Public Library")

    def test_its_initialism_does_too(self, spots: list[StudySpot]) -> None:
        # The expansion exists precisely because NYPL and its words share
        # almost no trigrams.
        assert expand("nypl") == '"New York Public Library"'
        assert "53rd Street Library" in names("nypl")

    def test_a_branch_that_names_no_system_is_not_dragged_in(self, spots: list[StudySpot]) -> None:
        # Baychester has no operator in the fixture.
        assert "Baychester Library" not in names("nypl")


class TestTypingAWordOut:
    """Search as you type.

    Postgres full text matches whole lexemes, so every keystroke before the
    last one used to find nothing and fall through to trigrams. Typing towards
    "Bobst" returned "The Cafe at Bob" -- confidently, and wrongly -- until the
    final letter landed.
    """

    @pytest.mark.parametrize("fragment", ["bob", "bobs", "bobst"])
    def test_a_fragment_reaches_the_name_it_starts(
        self, spots: list[StudySpot], fragment: str
    ) -> None:
        names = [spot.name for spot in search(fragment)]
        assert "Elmer Holmes Bobst Library" in names

    def test_a_fragment_of_a_later_word_works_too(self, spots: list[StudySpot]) -> None:
        # The distinctive word is third in the title, which is the case a
        # `startswith` on the name alone would miss.
        assert "Elmer Holmes Bobst Library" in [spot.name for spot in search("holm")]

    def test_every_word_has_to_match_something(self, spots: list[StudySpot]) -> None:
        # Prefixes are ANDed, exactly as whole words are, so a fragment that
        # belongs to no row still narrows rather than widens. Asserted on the
        # pass itself: `search` would go on to the trigram fallback, which is
        # designed to rescue exactly this and would mask the question.
        assert list(partial("bobst zzzz", StudySpot.objects.all())) == []

    def test_nonsense_still_returns_nothing(self, spots: list[StudySpot]) -> None:
        assert list(search("qqqq")) == []

    def test_a_complete_word_still_finds_everything_it_did(self, spots: list[StudySpot]) -> None:
        # The prefix form is a superset, so nothing that matched before stops
        # matching. It is a superset and not an equal: "library" now also
        # reaches a row whose word is "Libraries", which is the behaviour this
        # pass exists for.
        exact = {spot.name for spot in precise("library", StudySpot.objects.all())}
        assert exact <= {spot.name for spot in search("library")}

    def test_a_longer_word_is_reached_by_its_opening(self, spots: list[StudySpot]) -> None:
        # The real snapshot has "New York University Libraries"; this fixture
        # has none, so the same property is checked on a word it does have.
        assert "Elmer Holmes Bobst Library" in [spot.name for spot in search("librar")]

    @pytest.mark.parametrize("query", ['"Square Washington"', "washington -square", "a or b"])
    def test_an_operator_turns_this_pass_off(self, spots: list[StudySpot], query: str) -> None:
        # Quotes and `-` are intent, not noise. Prefixing their words would
        # silently answer a different question -- a quoted phrase asks for an
        # order, and ANDed prefixes have none.
        assert not is_plain(query)

    def test_punctuation_alone_matches_nothing(self, spots: list[StudySpot]) -> None:
        # No words means no tsquery to build, and a raw one built from an empty
        # string is a syntax error rather than an empty result.
        assert list(partial("...", StudySpot.objects.all())) == []


#: A library that is not NYU but holds every word of its name, scattered.
#:
#: This is the real shape of the bug: "New York" comes from the operator, and
#: "University" from the neighborhood, and neither has anything to do with the
#: other. 125th Street Library and Francis Martin Library both look like this.
DECOY = {
    "id": "facdb:decoy",
    "name": "Francis Martin Library",
    "category": "public_library",
    "no_purchase_needed": True,
    "operator": "New York Public Library",
    "address": "2150 University Avenue, Bronx, NY 10453",
    "neighborhood": "University Heights (South)-Morris Heights",
    "borough": "Bronx",
    "latitude": 40.8527,
    "longitude": -73.9101,
    "university": "Bronx Community College",
}


class TestAnInitialismExpandsToAPhrase:
    """Why the expansion is quoted.

    The vector spans four fields and full text ANDs bare words across all of
    them, so `new & york & university` matched any row holding "New" and
    "York" in one field and "University" in another. On the real snapshot
    typing NYU returned 21 spots and nine were other universities entirely.
    """

    @pytest.fixture
    def with_decoy(self, spots: list[StudySpot]) -> StudySpot:
        return StudySpot.objects.create(**DECOY)

    def test_the_expansion_is_a_phrase(self) -> None:
        assert expand("nyu") == '"New York University"'

    def test_a_word_that_is_not_an_initialism_is_not_quoted(self) -> None:
        # Quoting everything would make each word a one-word phrase, which is
        # harmless but says something the code does not mean.
        assert expand("library") == "library"

    def test_the_decoy_really_does_hold_every_word(self, with_decoy: StudySpot) -> None:
        # Guards the guard: if this stopped being true the test below would
        # pass for the wrong reason.
        haystack = f"{with_decoy.operator} {with_decoy.address} {with_decoy.neighborhood}".lower()
        assert all(word in haystack for word in ("new", "york", "university"))

    def test_it_is_not_returned_for_the_initialism(self, with_decoy: StudySpot) -> None:
        assert "Francis Martin Library" not in names("nyu")

    def test_the_places_that_are_nyu_still_are(self, with_decoy: StudySpot) -> None:
        assert "Elmer Holmes Bobst Library" in names("nyu")
