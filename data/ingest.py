"""Turn NYC Open Data into the normalized study-spot snapshot.

.. code-block:: text

    NYC Open Data ---\
    osm_cafes.json ----- ingest.py -> spots.json
    nyu_buildings.json /

Run it through just, which writes ``data/spots.json`` in place::

    just ingest

The snapshot stays in version control, so a checkout can load the serving table
and run the API without reaching the network. Regenerating it is how the data
changes; nothing writes to ``spots.json`` at runtime.

Where the records come from
---------------------------

Six sources. The first is the city's Facilities Database (FacDB, Socrata
``ji82-xba5``), which is what the ``facdb:`` identifier prefix refers to. Two
subsets of it are places a student might read in -- the ``LIBRARIES`` facility
group and the ``COLLEGES OR UNIVERSITIES`` subgroup.

The second is DOHMH Restaurant Inspection Results (``43nn-pn8j``), filtered to
``cuisine_description = 'Coffee/Tea'``, which the ``dohmh:`` prefix refers to and
which is where the cafes come from. FacDB holds none and never will: it
registers what the city *operates*, and a cafe is something the city
*inspects*. See "What a cafe is" below, because the obvious alternative is
wrong in a way that took a while to notice.

The third is Dining Out NYC (``fpeh-f7ci``), the register of outdoor-dining
licences. It is not a source of records -- it contributes no spot of its own --
only of one attribute: whether a cafe has sidewalk seating. See "Outdoor
seating is a join and not a category".

The fourth is ``nyu_buildings.json``, a hand-maintained list of NYU buildings
merged over the open-data records by :func:`combine`. FacDB registers NYU as an
institution and its schools as administrative points, but not the buildings
students study in, so without this list the snapshot has no campus study space
at all. Those records carry the ``nyu:`` identifier prefix and name the
institution whose building it is rather than a campus that happens to be within
500 m.

The fifth is the city's public Wi-Fi hotspot locations (``yjub-udmw``), used
only to answer one question: is there free public Wi-Fi at this spot. A hotspot
within 25 m sets ``free_public_wifi``. That radius is tight on purpose -- the
matches at 25 m are overwhelmingly hotspots the libraries themselves run, while
widening it to 100 m starts counting LinkNYC kiosks on the street, which is not
Wi-Fi anyone can use sitting down.

The sixth is ``osm_cafes.json``, the OpenStreetMap cafes written by ``osm.py``
from the Overpass API, which the ``osm:`` prefix refers to. It is **additive**:
DOHMH remains the spine for which establishments exist and where they are, and
OSM adds three attributes to the ones it can identify plus the cafes DOHMH files
under some other cuisine. ``osm.py``'s docstring says why a second cafe source
was needed and this one has the join; the short version is that
``cuisine_description`` is a food-safety code and ``amenity=cafe`` is a judgement
about what a place is, so Caffe Reggio -- on MacDougal Street since 1927, filed
by DOHMH as ``Italian`` -- is in one and not the other.

Neighborhood names and borough come from the 2020 Neighborhood Tabulation Areas
(``9nt8-h7nd``), which is read two different ways. FacDB publishes the NTA code
but not its name, so a facility's neighborhood is a dictionary lookup on
``nta2020``. DOHMH publishes no 2020 code at all -- its ``nta`` column is the
2010 vintage, four characters where 2020 codes are six -- so a cafe's
neighborhood is found by locating its coordinates inside the boundary polygons.
Two paths for one field is not ideal, and the alternative was worse: joining
2010 codes to 2010 names would put two different neighborhood vocabularies in
one snapshot, and the ``neighborhood`` filter would then depend on which source
a spot came from.

``free_public_wifi`` is false for every curated NYU building, and that is
correct rather than missing: those buildings have Wi-Fi that needs NYU
credentials, and the field answers whether *anyone* can use it.

No *city* source lists hours, noise, or power outlets. The city publishes a link
to each Queens branch's page and a weekly total of open hours for NYPL branches,
neither of which is a schedule. OpenStreetMap does carry an ``opening_hours``
for about half its cafes, which is why ``opening_hours`` is now a field -- and it
is published as the raw OSM string rather than turned into an "open now", which
needs a timezone and the public-holiday calendar the syntax can refer to. No
source lists noise, outlets, or access conditions, and the contract has no field
for any of them: several curated buildings require a university ID to enter.

Three states, not two
---------------------

``indoor_seating``, ``venue_wifi`` and ``opening_hours`` are the only fields in
the contract that are null for *unrecorded* rather than for *not applicable*,
and nothing downstream may collapse the two. ``venue_wifi = false`` is a
contributor who went and looked and found no Wi-Fi; ``venue_wifi = null`` is
nobody having said. That distinction is the reason OpenStreetMap is read at all,
and it is also why ``venue_wifi`` is a separate field from
``free_public_wifi`` rather than merged into it. They are different claims:
``venue_wifi`` is the venue's own Wi-Fi, and ``free_public_wifi`` is a hotspot
*the city publishes* within 25 m of the point, which is usually a library's own
and occasionally a LinkNYC kiosk. A cafe can easily have the first and not the
second.

What a cafe is
--------------

A cafe is an establishment the health department records as serving coffee or
tea. It is **not** a place that holds an outdoor-dining licence, which is what
this importer published as ``cafe`` until this was fixed.

Dining Out NYC is a register of outdoor-dining licences, and every row of it
was assigned ``category = "cafe"`` on the strength of holding one. A sidewalk
licence says a business puts tables on the pavement; it says nothing whatever
about what the business sells. Of the 1,652 records that reached the snapshot
that way, about 261 read as bars, pubs, pizzerias or restaurants -- "Good Bar",
"P.Mcdaid's Irish Pub", "Mchale's Bar & Grill", "Koronet Pizza" -- against about
179 whose name reads like a coffee shop. The application was telling students
an Irish pub was a cafe. It also missed every indoor-only coffee shop in the
city, because a cafe with no pavement tables has no licence and so had no row.

DOHMH's ``cuisine_description`` is the health department's own classification of
what an establishment serves, which is the question the category is supposed to
answer. Filtering it to ``Coffee/Tea`` yields 2,225 establishments where the
licence register yielded 1,652 mislabelled ones.

What this source does *not* support, and what the old comment here was right
about: it is an inspection log rather than a directory of open businesses. The
mitigations are specific and limited, and are spelled out at
:data:`CLOSURE_ACTION` and :func:`establishments`. In particular, a place that
quietly shut without a final inspection is still in here, and nothing in the
data says so.

Outdoor seating is a join and not a category
--------------------------------------------

Dining Out NYC is still read, but for one boolean rather than for the records
themselves. A licence whose name *and* street address match a DOHMH
establishment's sets ``outdoor_seating`` on that cafe.

The match is deliberately strict -- see :func:`outdoor_dining_index` -- because
the failure modes are not symmetric. A cafe whose licence was not found reads
as ``outdoor_seating = false``, which is what the field is documented to mean:
no matching licence, rather than no tables. A cafe credited with *someone
else's* licence is a false statement about a real business. Matching on street
address alone would do exactly that: 28 DOHMH cafes share a street address with
a sidewalk licence held under a different name, and inspecting them shows
almost all are a different business in the same building -- "787 Coffee" at 100
Lexington Ave shares its address with "Bhatti Indian Grill", "Joe Coffee" at
405 W 23 St with "Henry & The Lions". Those 28 are left unmatched on purpose.

Why the identifiers look like that
----------------------------------

An identifier is the source prefix and FacDB's own ``uid``, as in
``facdb:eec118768e15a5e03d3354abda7b00da``. The digest is upstream's, derived
from the source record, and this importer treats it as the record's identity
rather than computing one of its own.

That choice is about churn. ``load_spots`` replaces the whole table rather than
upserting, so an identifier derived from a record's *contents* -- its name,
address or coordinates -- would change every time the city fixed a typo or
re-geocoded a building, and every row of the snapshot would silently come back
as a different spot with the old one deleted. Anything holding an identifier,
including a bookmarked ``GET /spots/{id}``, would break for a cosmetic edit
upstream. Deriving the identifier from identity alone means re-running this
importer against unchanged upstream data produces a byte-identical snapshot,
and a changed name is an update to one row.

The prefix is not decoration: it keeps a second source from colliding with
FacDB if its keys happen to look the same, and it says where a record came
from.

What normalization does
-----------------------

Presentation is part of it. FacDB writes names and addresses in capitals, and
the published contract shows "125th Street Library" rather than "125TH STREET
LIBRARY", so this module title-cases both. Coordinates are rounded to six
decimal places, about a tenth of a metre, which is finer than a building and
keeps the snapshot small.

``address``, ``neighborhood`` and ``university`` are absent for some records.
They are written as ``null``, never as an empty string: the contract
distinguishes the two and the API returns ``null``.

``university`` is proximity and nothing else
--------------------------------------------

It names the closest campus within 500 metres, or the campus itself for a
campus record, and is ``null`` when no campus is that close. The campus list is
curated -- it is the higher-education subset of FacDB named above, the same
records this importer publishes as ``university`` spots -- and the field is
never guessed from a facility's name, its operator, or anything else.

A named campus is not an affiliation, an endorsement, or a claim that anyone
may walk in: 169 metres is what the data says about "125th Street Library" and
"Touro University - Harlem", and it says nothing more than that.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: ``data/ingest.py`` -> ``data/``.
HERE = Path(__file__).resolve().parent

DEFAULT_OUTPUT = HERE / "spots.json"

#: Trimmed upstream responses, so the tests and `--fixtures` need no network.
DEFAULT_FIXTURES = HERE / "fixtures"

SOCRATA_DOMAIN = "data.cityofnewyork.us"

#: Facilities Database. The ``facdb:`` identifier prefix names this dataset.
FACILITIES_DATASET = "ji82-xba5"
FACILITIES_WHERE = "facgroup = 'LIBRARIES' OR facsubgrp = 'COLLEGES OR UNIVERSITIES'"

#: 2020 Neighborhood Tabulation Areas, for the names FacDB only codes.
NEIGHBORHOODS_DATASET = "9nt8-h7nd"

#: Public Wi-Fi hotspots, for the one amenity the open data can support.
#:
#: Only the free ones: the dataset also carries "Limited Free", which means a
#: trial or a time limit, and a filter that promised Wi-Fi and delivered thirty
#: minutes of it would be worse than not offering the filter.
WIFI_DATASET = "yjub-udmw"
WIFI_WHERE = "type = 'Free'"

#: DOHMH Restaurant Inspection Results, the health department's register of
#: inspected food-service establishments. The ``dohmh:`` identifier prefix names
#: this dataset.
#:
#: FacDB is a register of *city facilities*, which is why it holds libraries and
#: campuses and not a single cafe. The city does not operate cafes, but it does
#: inspect them, and the inspector records what each one serves.
CAFES_DATASET = "43nn-pn8j"

#: Coffee shops, as the health department classifies them.
#:
#: ``cuisine_description`` is one value per establishment, chosen by DOHMH from a
#: fixed list, and ``Coffee/Tea`` is its entry for a coffee shop. This is the
#: whole of the category test: the importer does not read names, because
#: deciding what a business is from the words in its name is guessing, and the
#: previous version of this file guessed wrong 1,652 times.
CAFES_WHERE = "cuisine_description = 'Coffee/Tea'"

#: One row per inspection, so paging must be ordered on a column of the dataset
#: and the rows must then be folded down to one per establishment.
CAFES_ORDER = "camis"

#: Dining Out NYC, the city's register of outdoor-dining licences and the
#: successor to the retired DCA sidewalk-cafe dataset.
#:
#: Read for the ``outdoor_seating`` attribute only. It published no spot of its
#: own after the ``cafe`` category stopped meaning "holds a sidewalk licence";
#: see the module docstring.
OUTDOOR_DINING_DATASET = "fpeh-f7ci"

#: Issued sidewalk licences only.
#:
#: ``license_status`` also carries applications that were never granted, and
#: crediting a cafe with seating on the strength of an ungranted application
#: would be a false statement about a real business. ``Sidewalk`` rather than
#: ``Roadway`` because a roadway licence is a dining structure in a parking
#: lane, which is seasonal, frequently removed, and not somewhere to sit with a
#: laptop.
OUTDOOR_DINING_WHERE = "license_status = 'Issued' AND license_type = 'Sidewalk'"

SOURCE_PREFIX = "facdb"
CAFE_PREFIX = "dohmh"

#: OpenStreetMap cafes, written by ``osm.py``. The ``osm:`` identifier prefix
#: names this source.
#:
#: Not fetched here. One Overpass request takes about 45 seconds against a
#: volunteer-run service, so it is committed and refreshed on its own, the way
#: the subway station list is. See ``osm.py`` for what the source is and why it
#: is read at all.
OSM_CAFES_PATH = HERE / "osm_cafes.json"
OSM_PREFIX = "osm"

#: How far apart a DOHMH establishment and an OSM cafe that agree on **name and
#: street address** may be and still be taken for the same storefront.
#:
#: A backstop, exactly like :data:`OUTDOOR_MATCH_RADIUS_METRES`: the match is the
#: name and the address agreeing, and this only rejects a pair whose two
#: geocodes disagree so badly that one of them must be wrong. Of the 438 pairs
#: that agree on both, one is 1,340 m apart and it is the only one past this.
OSM_ADDRESS_MATCH_RADIUS_METRES = 200.0

#: How close an OSM cafe that agrees on **name alone** has to be before the name
#: is taken as identifying the same business.
#:
#: Name alone is not a storefront, and for a chain it is barely a hint: there are
#: over a hundred Starbucks in the register and the name tells them apart not at
#: all. Measured instead: among the pairs that agree on name *and* address, the
#: two sources' geocodes sit a median 18 m apart, 90% within 49 m and 95% within
#: 68 m. 150 m is past all but the long tail of that, which is the point -- an
#: OSM "Starbucks" 150 m from a DOHMH "Starbucks" is that Starbucks, while one
#: 400 m away is a different branch and must not inherit its attributes.
OSM_NAME_MATCH_RADIUS_METRES = 150.0

#: How close a DOHMH cafe has to be before an *unmatched* OSM cafe is treated as
#: possibly the same storefront under a different name, and skipped.
#:
#: This is the whole of the duplicate problem. 496 OSM cafes sit within 30 m of a
#: DOHMH cafe whose name does not match, and reading forty of them by hand, about
#: half are plainly one business written two ways -- "La Colombe Coffee Roasters"
#: and "La Colombe", "Coffee Project New York" and "Coffee Project NY",
#: "Devoción" and "Devocion" -- while the other half are plainly two businesses
#: next door to each other: "Rise Brewing Company" at 79 Delancey and
#: "Starbucks" at 80, "Grabstein's Bagels" at 651 Broadway and "Gregory's
#: Coffee" at 649. Proximity cannot tell those apart, so :func:`merge_osm_cafes`
#: uses the street address to, and falls back to skipping.
#:
#: 75 m is the 95th percentile of how far the two sources' geocodes sit apart
#: for a pair that agrees on name and address -- that is, how far one storefront
#: can appear to move between the two registers. Past it, two records are two
#: places.
OSM_SAME_STOREFRONT_METRES = 75.0

#: The category every DOHMH ``Coffee/Tea`` establishment takes.
CAFE_CATEGORY = "cafe"

#: A hand-maintained list of NYU buildings, kept as data rather than code so it
#: can be edited without touching the importer.
#:
#: FacDB is a register of city facilities, so it carries NYU as an institution
#: and its schools as administrative points, but none of the buildings students
#: actually study in. These ten are recorded by hand from public building
#: information. They are the reason the snapshot has campus study space at all.
CURATED_PATH = HERE / "nyu_buildings.json"

#: The identifier prefix the curated buildings carry.
#:
#: Named here rather than only in the JSON because two things now depend on
#: knowing which records were written by hand: :func:`curated_spots` checks
#: them against the contract, and :func:`drop_curated_duplicates` lets them win
#: against an open-data record describing the same building.
CURATED_PREFIX = "nyu"

#: The station list written by subway.py. Not a study-spot source: it exists so
#: every spot can say which trains are near it.
SUBWAY_PATH = HERE / "subway_stations.json"

#: How far a station can be before the answer is "none nearby" rather than a
#: number nobody would act on.
#:
#: 91% of spots have one inside 800 m. Past this the furthest is 7.7 km, on
#: Staten Island, where the railway is not the subway.
SUBWAY_RADIUS_METRES = 1200.0

#: Metres a minute, for turning a distance into something readable. Roughly
#: 4.8 km/h, which is an unhurried walk rather than a commuter's.
WALKING_METRES_PER_MINUTE = 80.0

#: How far counts as "around here" when counting a spot's neighbours.
#:
#: About a five-minute walk. The medians it produces separate the boroughs
#: cleanly -- Manhattan 32, Brooklyn 9, Queens 6, Bronx 1, Staten Island 2 --
#: which is what a reader would recognise as the difference between a dense
#: stretch and an isolated branch.
NEARBY_RADIUS_METRES = 400.0

#: Socrata serves at most 1,000 rows per request.
PAGE_SIZE = 1000

#: Anonymous requests share one throttled pool. A token raises the limit and is
#: free; it is read from the environment so it never reaches version control.
APP_TOKEN_VARIABLE = "NYC_OPEN_DATA_APP_TOKEN"

HTTP_TIMEOUT_SECONDS = 60

#: NYC Open Data asks for identifiable traffic and sheds load under pressure.
#: Two requests do not need a budget, but paging politely costs nothing.
PAGE_DELAY_SECONDS = 0.25
USER_AGENT = "StudySpot-ingest/1.0 (+https://github.com/gcivil-nyu-org/team-4-fall26)"

#: The fields ``load_spots`` accepts. A tenth field fails the load rather than
#: being dropped, so the importer checks its own output against this.
CONTRACT_FIELDS = (
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
)

#: The three fields that come from OpenStreetMap, and the only three in the
#: contract that are ``None`` for *unrecorded* rather than for *not applicable*.
#:
#: Every other nullable field is null because the record has no such thing: a
#: cafe has no operator, a spot with no station within 1.2 km has no station.
#: These three are null because nobody has written the answer down, and the
#: difference is the reason OSM is read. ``internet_access = no`` is somebody
#: who went and looked; ``free_public_wifi = false`` only ever meant that no
#: hotspot the city publishes is within 25 m. Collapsing unknown into false
#: would turn the absence of evidence into a claim.
OSM_FIELDS = ("indoor_seating", "venue_wifi", "opening_hours")

#: Categories where sitting down costs nothing.
#:
#: The question a student actually asks -- "can I work here without buying
#: something?" -- which no single category answers: true of every library and
#: of the campus buildings, false only of cafes.
#:
#: **About money and not entry.** A special library may be open by appointment,
#: an academic library may want a university ID, and an NYU building wants NYU
#: credentials. The contract has no field for access and the application
#: promises none; this one says only that nobody will ask you to buy a coffee.
#:
#: An allowlist rather than its inverse, so a category added below is not
#: silently published as free: whoever adds one has to decide.
NO_PURCHASE_CATEGORIES = frozenset(
    {
        "public_library",
        "special_library",
        "academic_library",
        "university_building",
    }
)

#: The published category vocabulary, keyed on FacDB's most specific type so
#: that a new upstream type fails loudly instead of landing in a near-enough
#: bucket. ``None`` is a deliberate exclusion rather than a missing mapping.
#:
#: ``PUBLIC LIBRARY`` and ``SPECIAL LIBRARIES`` are kept apart rather than both
#: published as libraries, because the difference is the one a reader cares
#: about. A branch of NYPL, BPL or QPL is somewhere anyone can walk into; a
#: special library is an institutional collection -- a club's, a society's, a
#: hospital's -- and many are open by appointment or to members only. Publishing
#: the second as ``public_library`` would claim access the data does not
#: support, which is the same overclaim ``free_public_wifi`` and ``university``
#: are each worded to avoid.
#:
#: The NYCHA community centre library is a city-run facility open to the
#: community it sits in, so it goes with the public branches.
CATEGORY_BY_FACILITY_TYPE: dict[str, str | None] = {
    "PUBLIC LIBRARY": "public_library",
    "NYCHA COMMUNITY CENTER - LIBRARY": "public_library",
    "SPECIAL LIBRARIES": "special_library",
    "ACADEMIC LIBRARIES": "academic_library",
    "2 YEAR INDEPENDENT": "university",
    "2 YEAR PROPRIETARY": "university",
    "4 YEAR PROPRIETARY": "university",
    "4-YEAR INDEPENDENT": "university",
    "CUNY - 4 YEAR COLLEGE": "university",
    "CUNY - COMMUNITY COLLEGE": "university",
    "CUNY - GRADUATE CENTER": "university",
    "GRADUATE PROGRAMS ONLY": "university",
    "SUNY - COMMUNITY COLLEGES": "university",
    "SUNY - HEALTH SCIENCE CENTERS": "university",
    "SUNY - SPECIALIZED COLLEGES": "university",
    # Someone's home. Listing it as a place to study would invite people to a
    # residence.
    "UNIVERSITY RESIDENTIAL STRUCTURE": None,
}

#: How close a free hotspot has to be before the spot is credited with it.
#:
#: Measured rather than chosen. At 25 m, 203 of the 248 public libraries match,
#: and almost every match is a hotspot the library itself operates -- NYPL, QPL
#: and BPL run 214 of them. Widen it to 100 m and the count rises to 274, but
#: the additions are LinkNYC kiosks on the street rather than Wi-Fi anyone can
#: use sitting down, which is the question the field is meant to answer.
WIFI_RADIUS_METRES = 25.0

CAMPUS_CATEGORY = "university"

#: Close enough to walk out of one and into the other.
CAMPUS_RADIUS_METRES = 500.0

BOROUGH_BY_FACILITY_BOROUGH = {
    "MANHATTAN": "Manhattan",
    "BROOKLYN": "Brooklyn",
    "QUEENS": "Queens",
    "BRONX": "Bronx",
    "STATEN ISLAND": "Staten Island",
}

#: About a tenth of a metre, and what the published example record shows.
COORDINATE_DIGITS = 6

#: A generous box around the five boroughs, as (south, north, west, east).
#:
#: The model already rejects a latitude outside -90..90, which catches a null
#: island or a swapped pair and nothing else. Upstream geocoding fails in a
#: narrower way: Dining Out placed "Enzo's of Arthur Ave" -- a real address in
#: the Bronx -- at 42.126441,-70.848088, which is in Massachusetts Bay. The
#: record passed every check, and would have put a Bronx restaurant in the
#: Atlantic on any map and given it a nearest subway 284 km away.
#:
#: DOHMH fails the same way for its own reasons: its rows that miss this box
#: are ``0, 0`` or carry an out-of-state zip -- a "Columbus Ave" with Mount
#: Vernon's 10550, a "Central Ave" with Jersey City's 07307. Those rows have no
#: coordinates at all either, so the box and the null check catch the same 42
#: establishments between them.
#:
#: Deliberately loose: the point is to catch a record in another state, not to
#: adjudicate the waterline. For a cafe the precise test is the point-in-polygon
#: pass in :func:`locate_nta`, which runs afterwards against the real
#: boundaries.
NYC_BOUNDS = (40.47, 40.93, -74.30, -73.68)

#: What DOHMH writes in ``action`` when an inspection closed the place.
#:
#: Case-insensitive on purpose: the dataset carries both "Establishment Closed
#: by DOHMH" and "Establishment re-closed by DOHMH", and a case-sensitive
#: ``LIKE '%Closed%'`` silently misses the second. It must also not match
#: "Establishment re-opened by DOHMH", which is the record of a place opening
#: again and contains no form of the word.
#:
#: **This catches inspection-ordered closures and nothing else.** A cafe that
#: shut quietly, without a final inspection to record it, is still in the
#: dataset and still in this snapshot. There is no field that would say so.
CLOSURE_ACTION = re.compile(r"\bre-?closed\b|\bclosed\b", re.IGNORECASE)

#: How far apart a DOHMH establishment and a Dining Out licence may be and still
#: be taken for the same storefront.
#:
#: A backstop rather than the test: the match is made on name and address, and
#: this only rejects a pair whose two geocodes disagree so badly that one of
#: them must be wrong. No pair that matched on name and address was rejected by
#: it, which is the result worth recording -- it fires on nothing today and is
#: here so that a future re-geocode cannot quietly move a licence across town.
OUTDOOR_MATCH_RADIUS_METRES = 200.0

EARTH_RADIUS_METRES = 6_371_000.0

#: Initialisms FacDB shouts for a reason, and which title case would mangle.
#: Every one of these appears in the facilities the importer publishes; a type
#: this list has not caught yet shows up as "Cuny" in the snapshot.
INITIALISMS = frozenset(
    {
        "AMG",
        "CUNY",
        "IE",
        "LIU",
        "MCNY",
        "NY",
        "NYADI",
        "NYC",
        "NYFA",
        "NYU",
        "SI",
        "SNFL",
        "SUNY",
    }
)

MINOR_WORDS = frozenset(
    {"a", "an", "and", "at", "by", "for", "from", "in", "of", "on", "or", "the", "to"}
)

#: "125TH STREET" is a street number, not emphasis.
ORDINAL = re.compile(r"^(\d+)(ST|ND|RD|TH)$", re.IGNORECASE)

#: Keeps an apostrophe inside its word, so "ST JOHN'S" does not become
#: "St John'S", and keeps every other run of punctuation as a separator, so
#: "100% COFFEE" keeps its per cent sign.
WORD_BOUNDARY = re.compile(r"([^\w']+)")

#: Street-type and direction words folded to one spelling before matching.
#:
#: The two registers write the same address differently and neither is wrong:
#: DOHMH stores "CENTRAL AVE" where Dining Out stores "1875 UTICA AVENUE". Only
#: the forms that actually occur in the two datasets are here, because an
#: abbreviation table nobody has checked against the data is a guess.
STREET_WORDS = {
    "AVENUE": "AVE",
    "AV": "AVE",
    "STREET": "ST",
    "STR": "ST",
    "ROAD": "RD",
    "PLACE": "PL",
    "BOULEVARD": "BLVD",
    "BLV": "BLVD",
    "DRIVE": "DR",
    "LANE": "LN",
    "COURT": "CT",
    "TERRACE": "TER",
    "PARKWAY": "PKWY",
    "PLAZA": "PLZ",
    "SQUARE": "SQ",
    "HIGHWAY": "HWY",
    "TURNPIKE": "TPKE",
    "CIRCLE": "CIR",
    "EXPRESSWAY": "EXPY",
    "NORTH": "N",
    "SOUTH": "S",
    "EAST": "E",
    "WEST": "W",
}

#: "5TH" and "5" are the same street. Dining Out writes one and DOHMH the other.
MATCH_ORDINAL = re.compile(r"^(\d+)(?:ST|ND|RD|TH)$")

#: How close a non-curated record sits to a curated building before it is
#: considered for being the same place.
#:
#: Deliberately small, and it is only half the test. See
#: :func:`drop_curated_duplicates` for the other half and for why distance
#: alone would delete nine good records to fix one duplicate.
CURATED_DUPLICATE_METRES = 50.0

#: Whether a published address begins with a house number, and so is a street
#: address rather than something else.
#:
#: FacDB puts a building name in the address column when it has no street for a
#: record -- "Elmer H Bobst Library, New York, NY 10012". That is the signature
#: of a row describing a *building* the curated list already covers, as opposed
#: to a place with an address of its own.
HOUSE_NUMBER = re.compile(r"^\s*\d")

#: Everything that is not a letter, a digit or a space, for match keys only.
#:
#: Separate from :data:`WORD_BOUNDARY`, which serves presentation and has to
#: keep punctuation. Here punctuation is noise: "TETE-A-TETE" and "TETE A TETE"
#: are one cafe, and "JEAN'S" and "JEANS" are one name.
MATCH_NOISE = re.compile(r"[^0-9A-Z ]+")


class IngestError(Exception):
    """The importer cannot produce a snapshot the loader would accept."""


@dataclass(frozen=True)
class Campus:
    """One entry of the curated campus list."""

    name: str
    latitude: float
    longitude: float


def warn(message: str) -> None:
    print(f"ingest: {message}", file=sys.stderr)


# -- Upstream ----------------------------------------------------------------


def socrata_page(dataset: str, params: dict[str, Any], token: str | None) -> list[Any]:
    url = f"https://{SOCRATA_DOMAIN}/resource/{dataset}.json?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
    )
    if token:
        request.add_header("X-App-Token", token)

    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 429:
            raise IngestError(
                "NYC Open Data is throttling this client. Request a free app token at "
                f"https://{SOCRATA_DOMAIN}/profile/edit/developer_settings and export it as "
                f"{APP_TOKEN_VARIABLE}."
            ) from error
        detail = error.read(100).decode("utf-8", "replace").strip()
        raise IngestError(
            f"NYC Open Data answered HTTP {error.code} for dataset {dataset}: {detail}"
        ) from error
    except urllib.error.URLError as error:
        raise IngestError(
            f"Could not reach {SOCRATA_DOMAIN} ({error.reason}). "
            "Pass --fixtures to run against the committed sample instead."
        ) from error

    if not isinstance(payload, list):
        raise IngestError(
            f"Dataset {dataset} answered with {type(payload).__name__}, not an array."
        )
    return payload


def socrata_rows(dataset: str, params: dict[str, Any], token: str | None, order: str) -> list[Any]:
    """Every row matching ``params``, one page at a time.

    ``order`` is a column of this dataset: ``$offset`` paging over an unordered
    query can repeat and skip rows.
    """
    rows: list[Any] = []
    offset = 0
    while True:
        page = socrata_page(
            dataset,
            {**params, "$order": order, "$limit": PAGE_SIZE, "$offset": offset},
            token,
        )
        rows.extend(page)
        if len(page) < PAGE_SIZE:
            return rows
        offset += PAGE_SIZE
        time.sleep(PAGE_DELAY_SECONDS)


def fixture_rows(directory: Path, name: str) -> list[Any]:
    path = directory / f"{name}.json"
    if not path.exists():
        raise IngestError(f"No fixture at {path}.")
    rows = json.loads(path.read_text("utf-8"))
    if not isinstance(rows, list):
        raise IngestError(f"{path} must contain an array of upstream records.")
    return rows


def read_sources(
    fixtures: Path | None,
) -> tuple[list[Any], list[Any], list[Any], list[Any], list[Any]]:
    """The raw upstream records, from the network or from a fixture directory."""
    if fixtures is not None:
        return (
            fixture_rows(fixtures, "facilities"),
            fixture_rows(fixtures, "cafes"),
            fixture_rows(fixtures, "outdoor_dining"),
            fixture_rows(fixtures, "neighborhoods"),
            fixture_rows(fixtures, "wifi"),
        )

    token = os.environ.get(APP_TOKEN_VARIABLE) or None
    if not token:
        warn(f"no {APP_TOKEN_VARIABLE} set; using the shared anonymous rate limit")

    facilities = socrata_rows(FACILITIES_DATASET, {"$where": FACILITIES_WHERE}, token, order="uid")
    cafes = socrata_rows(
        CAFES_DATASET,
        # Only the columns the snapshot or the join reads. The full row carries
        # the violation text for every inspection, which is 21,000 rows of prose
        # this importer has no use for.
        {
            "$select": (
                "camis,dba,boro,building,street,zipcode,latitude,longitude,inspection_date,action"
            ),
            "$where": CAFES_WHERE,
        },
        token,
        order=CAFES_ORDER,
    )
    outdoor_dining = socrata_rows(
        OUTDOOR_DINING_DATASET,
        {"$where": OUTDOOR_DINING_WHERE},
        token,
        # Dining Out publishes no stable row identifier, so paging is ordered on
        # Socrata's own row id: without a total order the pages can overlap and
        # drop records between them.
        order=":id",
    )
    neighborhoods = socrata_rows(
        NEIGHBORHOODS_DATASET,
        # The boundary geometry is about 4.5 MB, which this does now have to
        # download: DOHMH publishes no 2020 NTA code, so a cafe is placed by
        # locating its coordinates rather than by looking a code up. One request
        # serves both readings -- the code-to-name map for FacDB and the polygons
        # for the cafes -- so there is one definition of what an NTA is.
        {"$select": "nta2020,ntaname,boroname,the_geom"},
        token,
        order="nta2020",
    )
    hotspots = socrata_rows(
        WIFI_DATASET,
        # Coordinates are all the proximity test needs; the rest of the row is
        # provider metadata.
        {"$select": "objectid,latitude,longitude", "$where": WIFI_WHERE},
        token,
        order="objectid",
    )
    return facilities, cafes, outdoor_dining, neighborhoods, hotspots


# -- Normalization -----------------------------------------------------------


def text(value: Any) -> str | None:
    """A trimmed string, or ``None`` for anything upstream left blank."""
    if not isinstance(value, str):
        return None
    collapsed = " ".join(value.split())
    return collapsed or None


def title_word(word: str, *, minor_allowed: bool) -> str:
    stem, apostrophe, suffix = word.partition("'")
    if apostrophe and suffix.upper() == "S" and stem.upper() in INITIALISMS:
        return f"{stem.upper()}'s"

    shouted = word.upper()
    if shouted in INITIALISMS:
        return shouted

    ordinal = ORDINAL.match(word)
    if ordinal:
        return f"{ordinal.group(1)}{ordinal.group(2).lower()}"

    # A one-letter word is a middle initial far more often than it is an
    # article: "STEPHEN A. SCHWARZMAN BUILDING".
    if minor_allowed and len(word) > 1 and word.lower() in MINOR_WORDS:
        return word.lower()

    if shouted.startswith("MC") and len(word) > 3 and word.isalpha():
        return f"Mc{word[2:].capitalize()}"

    return word.capitalize()


def title_case(value: str) -> str:
    """Make a shouted FacDB string readable.

    Best effort, and deliberately so: the alternative to a short rule set is
    showing people "125TH STREET LIBRARY", which the published contract does
    not. Mixed-case input is normalized the same way, because FacDB is not
    consistent about which rows shout.
    """
    parts = WORD_BOUNDARY.split(" ".join(value.split()))
    words = [index for index, part in enumerate(parts) if index % 2 == 0 and part]
    rebuilt: list[str] = []
    separator = ""
    for index, part in enumerate(parts):
        if index % 2:
            separator = part
            rebuilt.append(part)
            continue
        if not part:
            continue
        # A minor word only stays lowercase in the middle of a phrase. After a
        # bracket or a dash it begins one -- "Juilliard School (The)", "Rose
        # Hill-Lincoln" -- and FacDB truncates long names mid-word, which leaves
        # a trailing "A" that is not an article.
        inside = index not in (words[0], words[-1]) and separator.isspace()
        rebuilt.append(title_word(part, minor_allowed=inside))
    return "".join(rebuilt)


def operator(record: dict[str, Any]) -> str | None:
    """Who runs the place, where the city records it.

    This is the one field that connects a branch to its library system, and
    nothing else in the record does. A branch is named after its neighborhood --
    "Howard Beach", "Fresh Meadows", "Glendale" -- so without this there is no
    way to find the 67 Queens Public Library branches by asking for them.

    FacDB fills it meaningfully for the 226 public branches (91 New York Public
    Library, 68 Brooklyn, 67 Queens) and repeats the facility's own name for the
    academic and special libraries, where it adds nothing and does no harm.

    Not title-cased. Upstream already capitalises this field, unlike ``facname``,
    and running it through title_case() would leave "Nyu Tamiment Library"
    exactly as wrong as it arrives.
    """
    return text(record.get("opname"))


def spot_id(record: dict[str, Any]) -> str:
    uid = text(record.get("uid"))
    if not uid:
        raise IngestError(f"An upstream record has no uid: {record.get('facname')!r}.")
    return f"{SOURCE_PREFIX}:{uid}"


def category(record: dict[str, Any]) -> str | None:
    """The published category, or ``None`` for a deliberately excluded type."""
    facility_type = text(record.get("factype"))
    if facility_type is None:
        raise IngestError(f"Record {spot_id(record)} has no facility type.")
    try:
        return CATEGORY_BY_FACILITY_TYPE[facility_type.upper()]
    except KeyError:
        # Inventing a category here would publish a guess as data, and mapping
        # it to the nearest existing one would bury the change. FacDB added a
        # type; someone has to decide what it is.
        raise IngestError(
            f"Record {spot_id(record)} has the unmapped facility type {facility_type!r}. "
            "Add it to CATEGORY_BY_FACILITY_TYPE, or map it to None to exclude it."
        ) from None


def borough(record: dict[str, Any]) -> str:
    name = text(record.get("boro"))
    if name is None:
        raise IngestError(f"Record {spot_id(record)} has no borough.")
    try:
        return BOROUGH_BY_FACILITY_BOROUGH[name.upper()]
    except KeyError:
        raise IngestError(
            f"Record {spot_id(record)} is in {name!r}, which is not one of the five boroughs."
        ) from None


def street_address(record: dict[str, Any]) -> str | None:
    """The address as the contract publishes it, or ``None``.

    FacDB leaves the street address off a few dozen library branches. The
    remaining pieces -- a city and a zip code -- are not an address, so the
    field stays null rather than becoming ", New York, NY 11208".
    """
    street = text(record.get("address"))
    if street is None:
        return None

    parts = [title_case(street)]
    city = text(record.get("city"))
    if city:
        parts.append(title_case(city))
    zipcode = text(record.get("zipcode"))
    parts.append(f"NY {zipcode}" if zipcode else "NY")
    return ", ".join(parts)


def neighborhood_names(rows: list[Any]) -> dict[str, str]:
    names: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        code = text(row.get("nta2020"))
        name = text(row.get("ntaname"))
        if code and name:
            names[code] = name
    if not names:
        raise IngestError("The neighborhood dataset supplied no 2020 NTA names.")
    return names


def neighborhood(record: dict[str, Any], names: dict[str, str], identifier: str) -> str | None:
    """The 2020 NTA name, or ``None`` when the source does not place the record.

    FacDB only: it publishes the 2020 code but not its name, so this is a
    dictionary lookup. DOHMH publishes no 2020 code -- its ``nta`` column is the
    2010 vintage -- so a cafe's neighborhood comes from :func:`locate_nta`
    instead, which tests the coordinates against the boundary polygons. See the
    module docstring for why one field is derived two ways.

    The identifier is passed in rather than derived so that the warning below
    can name the record; a caller that is not mapping a FacDB row has no ``uid``
    for :func:`spot_id` to read.
    """
    code = text(record.get("nta2020"))
    if code is None:
        return None
    name = names.get(code)
    if name is None:
        # The two datasets are revised on their own schedules, so a code can
        # outrun the boundary file. Publishing the code instead would put a
        # string like "MN1102" where the contract promises a name.
        warn(f"no 2020 NTA name for {code!r}; leaving {identifier} without a neighborhood")
    return name


def cafe_id(camis: str) -> str:
    """The identifier for one establishment.

    ``camis`` is the health department's own permit number for an establishment
    and is stable across inspections, which is exactly the property the module
    docstring asks an identifier for: it is upstream's notion of identity rather
    than a digest of the record's contents, so a re-geocode or a corrected
    street name moves one row of the snapshot instead of retiring a spot and
    inventing a new one.

    This is the one real gain from changing source that has nothing to do with
    the category. The previous cafe identifier was a hash of name and address
    because a licence register has no durable key, so renaming a cafe deleted it
    and created a stranger in its place.
    """
    return f"{CAFE_PREFIX}:{camis}"


def cafe_address(record: dict[str, Any]) -> str | None:
    """The address as the contract publishes it, or ``None``.

    DOHMH splits the street address into ``building`` and ``street`` where FacDB
    and Dining Out each keep one string, and stores both in upper case, so they
    are joined and title-cased here as the facility names are.

    A row with no ``street`` has no address worth publishing, and a row with a
    ``street`` but no ``building`` does: "Penn Station" and "JFK International
    Airport" are where several of these actually are.
    """
    street = text(record.get("street"))
    if street is None:
        return None

    building = text(record.get("building"))
    parts = [title_case(f"{building} {street}" if building else street)]
    zipcode = text(record.get("zipcode"))
    # No city: DOHMH records the borough in `boro`, and that column is the one
    # the module docstring calls uneven -- five establishments have "0". The
    # borough published on the record comes from the boundary polygon instead,
    # and repeating it inside the address string would mean trusting `boro`
    # again for presentation after refusing to trust it for data.
    parts.append(f"NY {zipcode}" if zipcode else "NY")
    return ", ".join(parts)


def cafe_coordinates(record: dict[str, Any]) -> tuple[float, float] | None:
    """A geocode inside :data:`NYC_BOUNDS`, or ``None``.

    Unlike :func:`coordinate` this returns ``None`` rather than raising for a
    value it cannot use. A facility with a broken coordinate is a bug in an
    import of 264 records and should stop the run; DOHMH ships 42 establishments
    with no geocode or with ``0, 0`` on any given day, and failing the whole
    snapshot over them would mean never publishing a cafe again.
    """
    raw_latitude, raw_longitude = record.get("latitude"), record.get("longitude")
    if raw_latitude in (None, "") or raw_longitude in (None, ""):
        return None
    try:
        latitude, longitude = float(raw_latitude), float(raw_longitude)
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(latitude) and math.isfinite(longitude)):
        return None
    if not in_new_york_city(latitude, longitude):
        return None
    return round(latitude, COORDINATE_DIGITS), round(longitude, COORDINATE_DIGITS)


def establishments(rows: list[Any]) -> dict[str, dict[str, Any]]:
    """One record per establishment: the most recent inspection of each.

    ``43nn-pn8j`` is one row per inspection -- 21,422 rows describing 2,225
    coffee shops -- so this is what turns an inspection log into a directory.
    The most recent row is the one whose ``action`` says whether the place is
    currently closed, and whose address and geocode are the freshest the city
    has.

    Ties are broken on ``record_date`` and then on nothing: two rows of the same
    inspection differ only in which violation they cite, and the fields this
    importer reads are identical across them. Measured rather than assumed --
    ``dba`` and ``(building, street)`` are constant within every single
    ``camis`` in the dataset, so there is no row here whose choice could change
    a published name or address.
    """
    by_camis: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise IngestError("An upstream record is not a JSON object.")
        camis = text(row.get("camis"))
        if camis is None:
            # Without the permit number there is no identity to publish under.
            continue
        by_camis.setdefault(camis, []).append(row)

    return {
        camis: max(
            group,
            key=lambda row: (row.get("inspection_date") or "", row.get("record_date") or ""),
        )
        for camis, group in by_camis.items()
    }


@dataclass(frozen=True)
class NtaArea:
    """One 2020 Neighborhood Tabulation Area, as a polygon with a bounding box.

    The bounding box is carried rather than recomputed because it turns the
    point-in-polygon pass from 262 polygon tests per cafe into the handful whose
    box the point falls inside.
    """

    name: str
    borough: str
    #: Outer ring first, then any holes, each a list of ``(longitude, latitude)``.
    rings: tuple[tuple[tuple[float, float], ...], ...]
    west: float
    south: float
    east: float
    north: float


def nta_areas(rows: list[Any]) -> list[NtaArea]:
    """The boundary polygons, for the records that arrive without an NTA code.

    A MultiPolygon becomes one :class:`NtaArea` per polygon rather than one per
    NTA: several neighborhoods are more than one piece of land, and testing each
    piece against its own bounding box is both simpler and faster than testing a
    box that spans the water between them.

    An NTA row with no geometry is not an error. The same request serves
    :func:`neighborhood_names`, which needs only the code and the name, and a
    trimmed fixture has no reason to carry 4.5 MB of coastline.
    """
    areas: list[NtaArea] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = text(row.get("ntaname"))
        borough = text(row.get("boroname"))
        geometry = row.get("the_geom")
        if name is None or borough is None or not isinstance(geometry, dict):
            continue
        if borough.upper() not in BOROUGH_BY_FACILITY_BOROUGH:
            raise IngestError(f"NTA {name!r} is in {borough!r}, which is not one of the five.")

        for polygon in geometry.get("coordinates") or ():
            rings: list[tuple[tuple[float, float], ...]] = []
            for ring in polygon:
                try:
                    points = tuple((float(x), float(y)) for x, y in ring)
                except (TypeError, ValueError):
                    raise IngestError(f"NTA {name!r} has a non-numeric boundary point.") from None
                if len(points) >= 3:
                    rings.append(points)
            if not rings:
                continue
            longitudes = [x for x, _ in rings[0]]
            latitudes = [y for _, y in rings[0]]
            areas.append(
                NtaArea(
                    name=name,
                    borough=BOROUGH_BY_FACILITY_BOROUGH[borough.upper()],
                    rings=tuple(rings),
                    west=min(longitudes),
                    south=min(latitudes),
                    east=max(longitudes),
                    north=max(latitudes),
                )
            )

    if not areas:
        raise IngestError("The neighborhood dataset supplied no 2020 NTA boundaries.")
    return areas


def point_in_ring(longitude: float, latitude: float, ring: tuple[tuple[float, float], ...]) -> bool:
    """Ray casting: whether a point is inside one closed ring.

    Counts the ring's edges crossed by a ray running east from the point. An odd
    count means inside. ``(y1 > latitude) != (y2 > latitude)`` is what makes a
    vertex count once rather than twice when the ray passes exactly through it,
    which is the usual way this algorithm is got wrong.

    A point exactly on the boundary may land either way. That is acceptable
    here and nowhere near the precision the field claims: two adjacent NTAs
    share an edge, and a cafe on it is in one neighborhood or the other.
    """
    inside = False
    count = len(ring)
    for index in range(count):
        first_longitude, first_latitude = ring[index]
        next_longitude, next_latitude = ring[(index + 1) % count]
        if (first_latitude > latitude) != (next_latitude > latitude):
            along = (latitude - first_latitude) / (next_latitude - first_latitude)
            if longitude < first_longitude + along * (next_longitude - first_longitude):
                inside = not inside
    return inside


def locate_nta(latitude: float, longitude: float, areas: list[NtaArea]) -> NtaArea | None:
    """The NTA whose boundary contains the point, or ``None``.

    Inside the outer ring and outside every hole. The holes matter: an NTA with
    another carved out of it would otherwise claim points belonging to its
    neighbor.
    """
    for area in areas:
        if not (area.west <= longitude <= area.east and area.south <= latitude <= area.north):
            continue
        if not point_in_ring(longitude, latitude, area.rings[0]):
            continue
        if any(point_in_ring(longitude, latitude, hole) for hole in area.rings[1:]):
            continue
        return area
    return None


def match_words(value: str | None) -> list[str]:
    """One spelling of a name or an address, for comparison and never for display.

    Upper-cased, stripped of punctuation, with street types and compass
    directions folded to one form and ordinals reduced to their number. The
    result is never published: it exists so that "1875 Utica Avenue" and "1875
    UTICA AVE" can be recognized as one address.
    """
    if not isinstance(value, str):
        return []
    words: list[str] = []
    for word in MATCH_NOISE.sub(" ", value.upper()).split():
        ordinal = MATCH_ORDINAL.match(word)
        if ordinal:
            word = ordinal.group(1)
        words.append(STREET_WORDS.get(word, word))
    return words


def match_key(value: str | None) -> str:
    return " ".join(match_words(value))


def outdoor_dining_index(rows: list[Any]) -> dict[tuple[str, str], list[tuple[float, float]]]:
    """Sidewalk licences keyed on ``(name, address)``, for the seating join.

    Both of a licence's names are indexed. ``assumed_name_s`` is the name over
    the door and is what DOHMH records too, but a few licences are held under
    the legal name alone, and DOHMH occasionally records that instead.

    The key is name *and* address because address alone is not a storefront. The
    module docstring has the measurement: 28 DOHMH cafes share a street address
    with a licence held under a different name, and inspecting them shows almost
    every one is a different business in the same building. Requiring the name
    too costs a handful of genuine matches -- "Tete A Tete Cafe" is licensed as
    "Tete-A-Tete" and keeps its seating, but a cafe licensed under a trading
    name DOHMH does not know reads as false -- and that is the direction to err
    in: ``false`` already means "no licence matched", while a wrong match is a
    claim about a real business that is simply untrue.

    The value is the licence's coordinates, so :func:`has_outdoor_seating` can
    reject a pair whose geocodes put them hundreds of metres apart.
    """
    index: dict[tuple[str, str], list[tuple[float, float]]] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise IngestError("An upstream record is not a JSON object.")
        address = match_key(row.get("street"))
        if not address:
            continue

        point: tuple[float, float] | None = None
        try:
            latitude, longitude = float(row["latitude"]), float(row["longitude"])
        except (TypeError, ValueError, KeyError):
            # A licence with no geocode still joins on name and address; there
            # is simply nothing for the distance backstop to check.
            point = None
        else:
            if math.isfinite(latitude) and math.isfinite(longitude):
                point = (latitude, longitude)

        for name in {
            match_key(row.get("assumed_name_s")),
            match_key(row.get("business_legal_name")),
        }:
            if not name:
                continue
            licences = index.setdefault((name, address), [])
            if point is not None:
                licences.append(point)

    return index


def has_outdoor_seating(
    record: dict[str, Any],
    latitude: float,
    longitude: float,
    index: dict[tuple[str, str], list[tuple[float, float]]],
) -> bool:
    """Whether a sidewalk licence matches this establishment's name and address.

    ``False`` means no licence matched, which is not the same as no outdoor
    seating: the licence may be held under a trading name the health department
    does not record, and the join is strict on purpose. The field is worded in
    the model to say exactly that, the same way ``free_public_wifi`` is.
    """
    name = match_key(record.get("dba"))
    building = text(record.get("building")) or ""
    address = match_key(f"{building} {text(record.get('street')) or ''}")
    if not name or not address:
        return False

    key = (name, address)
    if key not in index:
        return False

    points = index[key]
    if not points:
        # Matched on name and address, with no geocode on the licence to check
        # it against. The name and address agreeing is the match; the distance
        # is only a backstop, and a missing geocode is not evidence against.
        return True
    return any(
        haversine_metres(latitude, longitude, licence_latitude, licence_longitude)
        <= OUTDOOR_MATCH_RADIUS_METRES
        for licence_latitude, licence_longitude in points
    )


def cafe_spot(
    camis: str,
    record: dict[str, Any],
    areas: list[NtaArea],
    index: dict[tuple[str, str], list[tuple[float, float]]],
) -> dict[str, Any] | None:
    """Map one DOHMH establishment onto the contract, or ``None`` if it cannot be.

    ``dba`` is "doing business as", the name over the door, and is the only name
    the dataset carries -- which is a second small gain over the licence
    register, where the name was as likely to be "CGM-LLNR LLC" as "Jean's".

    Returns ``None`` rather than raising for a record that cannot be placed.
    Unlike a facility this must not fail the import: the register is maintained
    for inspections rather than for mapping, and a few dozen rows are
    ungeocoded at any given time.
    """
    name = text(record.get("dba"))
    address = cafe_address(record)
    point = cafe_coordinates(record)
    if name is None or address is None or point is None:
        return None

    latitude, longitude = point
    # Borough and neighborhood both come from the boundary polygon. DOHMH does
    # publish `boro`, and it agrees with the polygon for every one of the 2,166
    # establishments that reach this point -- but it is also "0" for five of
    # them, and a field that is right except when it is blank is not a field
    # worth reading when the polygon answers the same question exactly.
    area = locate_nta(latitude, longitude, areas)
    if area is None:
        # Inside the bounding box and outside every neighborhood: the geocode
        # is in the harbour or just over a county line. Nothing places it, and
        # the contract requires a borough.
        return None

    return {
        "id": cafe_id(camis),
        "name": title_case(name),
        "category": CAFE_CATEGORY,
        "address": address,
        "neighborhood": area.name,
        "borough": area.borough,
        "latitude": latitude,
        "longitude": longitude,
        # Filled in by normalize(), from the rest of the snapshot.
        "university": None,
        # DOHMH records the establishment, not who runs it. The old licence
        # register did carry `business_legal_name`, which was a registration
        # rather than an operator anyone would search for, so this field has
        # been null for cafes from the start and stays null.
        "operator": None,
        "free_public_wifi": False,
        # A cafe is where you buy something. That is what a cafe is.
        "no_purchase_needed": False,
        # Filled in by combine(), which is the only point that sees
        # every published spot including the curated ones.
        "subway_station": None,
        "subway_routes": None,
        "subway_metres": None,
        "subway_step_free": None,
        "nearby_spots": 0,
        "outdoor_seating": has_outdoor_seating(record, latitude, longitude, index),
        # Unrecorded until an OSM cafe is matched to this establishment by
        # merge_osm_cafes(). DOHMH inspects kitchens; it has no reason to know
        # whether there is somewhere to sit or Wi-Fi to use, and 1,721 of the
        # 2,158 establishments keep all three as null -- 437 are matched and
        # the rest are not. Null is the honest value: see OSM_FIELDS.
        "indoor_seating": None,
        "venue_wifi": None,
        "opening_hours": None,
    }


@dataclass(frozen=True)
class CafeIdentity:
    """A published cafe's name and street address, normalized for the OSM join.

    Built where the DOHMH row is still in hand rather than re-derived from the
    published record: :func:`cafe_address` appends ", NY 10012" for
    presentation, and taking that apart again to match on it would mean two
    spellings of one key and two places for them to disagree.
    """

    name: str
    address: str


@dataclass
class OsmMerge:
    """What :func:`merge_osm_cafes` did, for the importer to report.

    Every OSM record lands in exactly one of these, and the numbers are meant
    to be read: ``ambiguous`` being large is not a bug, it is the join refusing
    to guess. See :data:`OSM_SAME_STOREFRONT_METRES`.
    """

    #: DOHMH cafes that an OSM record identified and added attributes to.
    enriched: int = 0
    #: OSM cafes published as spots of their own, because nothing matched them
    #: and nothing was close enough to be them.
    added: int = 0
    #: OSM cafes dropped because they might be a DOHMH cafe and might not.
    ambiguous: int = 0
    #: OSM cafes outside :data:`NYC_BOUNDS`, or inside it and outside every
    #: neighborhood boundary. The Overpass bounding box is a rectangle and the
    #: city is not: the cafe at Turtle Back Zoo in West Orange, New Jersey is
    #: inside the box.
    unplaceable: int = 0


def osm_cafes(path: Path = OSM_CAFES_PATH) -> list[dict[str, Any]]:
    """The committed OSM cafe list, or an empty list when it has not been built.

    A warning rather than an error, the way :func:`subway_stations` is. Without
    it the snapshot is what it was before OSM was read -- DOHMH cafes with three
    unrecorded fields -- which is a smaller snapshot rather than a broken one.
    """
    if not path.exists():
        warn(f"no {path.name}; cafes will publish no OSM attributes. Run `just ingest-osm`.")
        return []
    cafes = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(cafes, list):
        raise IngestError(f"{path} must contain a JSON array of cafes.")
    return cafes


def osm_source(fixtures: Path | None) -> list[Any]:
    """The OSM cafes: the fixture sample under ``--fixtures``, the committed file otherwise.

    Unlike the subway list, which :func:`main` reads from the repository in
    either mode, this one changes how many records the snapshot has. A fixture
    run that read the real 2,978 would merge the whole city into eight
    establishments, and the suite would be testing a snapshot nobody ships.
    """
    if fixtures is not None:
        return osm_cafes(fixtures / f"{OSM_CAFES_PATH.name}")
    return osm_cafes(OSM_CAFES_PATH)


def osm_address(record: dict[str, Any]) -> str | None:
    """The address as the contract publishes it, or ``None``.

    The same shape :func:`cafe_address` produces, so a cafe reads the same
    whichever source it came from. Not title-cased, unlike every FacDB and DOHMH
    string: OSM is written by people in mixed case already, and ``title_case``
    would turn "MacDougal Street" into "Macdougal Street" -- which is what DOHMH
    publishes and what the one source that gets it right does not.

    A house number without a street is not an address. 2,140 of the 2,978 cafes
    carry a street and 412 of the ones this importer publishes carry neither,
    which is why the field is nullable in the first place.
    """
    street = text(record.get("street"))
    if street is None:
        return None

    house_number = text(record.get("house_number"))
    parts = [f"{house_number} {street}" if house_number else street]
    postcode = text(record.get("postcode"))
    parts.append(f"NY {postcode}" if postcode else "NY")
    return ", ".join(parts)


def osm_address_key(record: dict[str, Any]) -> str:
    """One OSM cafe's street address for the join, or ``""`` when it has none.

    **Both the house number and the street, or nothing.** A street on its own is
    not a storefront: "Broadway" cannot be compared with "123 Broadway" to
    decide whether two records are the same door, and letting it try would make
    the comparison *disagree* -- which is what the merge reads as evidence of
    two separate places. 26 of the 2,978 cafes carry a street with no number and
    7 a number with no street; they join on name and proximity like the 831 that
    carry neither, which is the right answer rather than a concession.

    The DOHMH side is built the same way in :func:`normalize`, except that a
    DOHMH establishment with no street has already been dropped by
    :func:`cafe_address`.
    """
    house_number = text(record.get("house_number"))
    street = text(record.get("street"))
    if house_number is None or street is None:
        return ""
    return match_key(f"{house_number} {street}")


def osm_attributes(record: dict[str, Any]) -> dict[str, Any]:
    """The three OSM fields, each true, false, or ``None`` for unrecorded.

    ``osm.py`` has already reduced the tags to these three states, so this only
    refuses a value that is not one of them. A contributed dataset read through
    a committed file is exactly where a hand-edit puts a string where a boolean
    belongs, and a stray ``"yes"`` would reach the model as ``True``.
    """
    attributes: dict[str, Any] = {}
    for field in OSM_FIELDS:
        value = record.get(field)
        if field == "opening_hours":
            attributes[field] = text(value)
            continue
        if value is not None and not isinstance(value, bool):
            raise IngestError(
                f"OSM cafe {record.get('id')!r} has a non-boolean {field}: {value!r}."
            )
        attributes[field] = value
    return attributes


def osm_spot(
    record: dict[str, Any],
    name: str,
    latitude: float,
    longitude: float,
    area: NtaArea,
) -> dict[str, Any]:
    """Map one OSM cafe onto the contract, as a spot of its own.

    Reached only for a record that matched no DOHMH establishment and had none
    close enough to be, so this is a cafe the health department files under some
    other cuisine -- Caffe Reggio, on MacDougal Street since 1927, which DOHMH
    records as ``Italian``.

    It is published on OSM's word alone, which is worth being clear about:
    ``amenity=cafe`` is a contributor's judgement and nothing re-checks that the
    place is still open. See the "What this does not establish" section of
    ``osm.py``.
    """
    return {
        "id": f"{OSM_PREFIX}:{record['id']}",
        "name": name,
        "category": CAFE_CATEGORY,
        "address": osm_address(record),
        "neighborhood": area.name,
        "borough": area.borough,
        "latitude": latitude,
        "longitude": longitude,
        # A cafe is a third place in its own right, not somewhere reached
        # through a campus. The same rule the DOHMH cafes follow.
        "university": None,
        # OSM has an `operator` tag, and it is deliberately not read. It is
        # filled for a chain outlet and for the Turtle Back Zoo cafe and empty
        # for the independents, and the field means "who runs the place, where
        # the city records it" -- this would be somewhere else recording it.
        "operator": None,
        # Filled in by normalize(), from the rest of the snapshot.
        "free_public_wifi": False,
        # A cafe is where you buy something.
        "no_purchase_needed": False,
        # Filled in by combine(), the only point that sees every published spot.
        "subway_station": None,
        "subway_routes": None,
        "subway_metres": None,
        "subway_step_free": None,
        "nearby_spots": 0,
        # No Dining Out licence was matched, because the join runs on DOHMH
        # establishments and this is not one. False here means what it means
        # everywhere: no licence matched. OSM's own `outdoor_seating` is not
        # read into it -- see osm.py for why a field that already has a narrow,
        # checkable meaning is not filled from a source with a different one.
        "outdoor_seating": False,
        **osm_attributes(record),
    }


def point_grid(
    spots: list[dict[str, Any]],
) -> dict[tuple[float, float], list[dict[str, Any]]]:
    """Spots bucketed onto a hundredth-of-a-degree grid, for proximity lookups.

    The same grid :func:`assign_nearby` builds, and usable for any radius up to
    about 850 m: a cell is roughly 1.1 km north-south and 850 m east-west in New
    York, so the eight neighbouring cells cover everything that close.
    """
    grid: dict[tuple[float, float], list[dict[str, Any]]] = {}
    for spot in spots:
        grid.setdefault((round(spot["latitude"], 2), round(spot["longitude"], 2)), []).append(spot)
    return grid


def within(
    latitude: float,
    longitude: float,
    grid: dict[tuple[float, float], list[dict[str, Any]]],
    radius: float,
) -> list[dict[str, Any]]:
    """Every gridded spot within ``radius`` metres of a point."""
    found: list[dict[str, Any]] = []
    for delta_latitude in (-0.01, 0.0, 0.01):
        for delta_longitude in (-0.01, 0.0, 0.01):
            cell = (
                round(latitude + delta_latitude, 2),
                round(longitude + delta_longitude, 2),
            )
            for spot in grid.get(cell, ()):
                if (
                    haversine_metres(latitude, longitude, spot["latitude"], spot["longitude"])
                    <= radius
                ):
                    found.append(spot)
    return found


def merge_osm_cafes(
    cafes: list[dict[str, Any]],
    identities: dict[str, CafeIdentity],
    records: list[Any],
    areas: list[NtaArea],
) -> tuple[list[dict[str, Any]], OsmMerge]:
    """Enrich the DOHMH cafes from OSM, and return the cafes OSM alone knows.

    **Additive and never substitutive.** DOHMH decides which establishments
    exist and what their addresses are; this adds attributes to the ones OSM can
    identify and publishes the ones it cannot match as spots of their own. No
    DOHMH record is dropped, renamed, moved or recategorized here.

    Matching is the dangerous part, and the asymmetry is the same one
    :func:`outdoor_dining_index` is written around: a cafe missing its OSM
    attributes reads as three unrecorded fields, which is exactly what they
    mean, while a cafe credited with *another business's* opening hours is a
    false statement about a real place. This project has already shipped a wrong
    join once, on ``operator``.

    So a match needs the normalized name **and** the location to agree, never
    one alone:

    * name and street address both agree, and the two geocodes are within
      :data:`OSM_ADDRESS_MATCH_RADIUS_METRES` of each other, or
    * the name agrees and the two points are within
      :data:`OSM_NAME_MATCH_RADIUS_METRES`.

    An OSM record that two DOHMH cafes both answer, or a DOHMH cafe that two OSM
    records both claim, is ambiguous and neither is joined -- one of the two
    would be wrong and nothing here says which.

    An OSM record that matched nothing is then tested the other way round,
    because the risk has turned over: publishing it would duplicate a cafe
    already in the snapshot under a differently-spelled name. If a DOHMH cafe
    sits within :data:`OSM_SAME_STOREFRONT_METRES` it is published only when both
    records carry a street address and the two addresses differ, which is the
    one piece of evidence available that they are two storefronts rather than
    one. Otherwise it is ambiguous and dropped. Dropping it costs recall, which
    is the thing this source was added to fix, so it is worth saying what the
    alternative costs: a second pin for one cafe, twice in the result list, two
    detail pages, and both of them half right.
    """
    by_name: dict[str, list[dict[str, Any]]] = {}
    for spot in cafes:
        by_name.setdefault(identities[spot["id"]].name, []).append(spot)
    grid = point_grid(cafes)

    merge = OsmMerge()
    # Which OSM record enriched which cafe, so that a second claim on the same
    # cafe can be recognized as the ambiguity it is rather than overwriting the
    # first and depending on the order the file happened to be read in.
    claimed: dict[str, str] = {}
    added: list[dict[str, Any]] = []

    for record in records:
        if not isinstance(record, dict):
            raise IngestError("An OSM cafe is not a JSON object.")

        name = text(record.get("name"))
        identifier = text(record.get("id"))
        if name is None or identifier is None:
            # osm.py drops both of these before writing the file, so reaching
            # here means the file was hand-edited.
            raise IngestError(f"An OSM cafe has no name or no id: {record!r}.")

        try:
            latitude = round(float(record["latitude"]), COORDINATE_DIGITS)
            longitude = round(float(record["longitude"]), COORDINATE_DIGITS)
        except (KeyError, TypeError, ValueError):
            raise IngestError(f"OSM cafe {identifier!r} has unusable coordinates.") from None

        name_key = match_key(name)
        address_key = osm_address_key(record)

        candidates = []
        for spot in by_name.get(name_key, ()):
            metres = haversine_metres(latitude, longitude, spot["latitude"], spot["longitude"])
            agrees_on_address = bool(address_key) and identities[spot["id"]].address == address_key
            if (agrees_on_address and metres <= OSM_ADDRESS_MATCH_RADIUS_METRES) or (
                metres <= OSM_NAME_MATCH_RADIUS_METRES
            ):
                candidates.append(spot)

        if len(candidates) > 1:
            # The same name within walking distance twice. Two Starbucks either
            # side of one street is the common case, and crediting one of them
            # with the other's hours is a coin toss.
            merge.ambiguous += 1
            continue

        if candidates:
            spot = candidates[0]
            if spot["id"] in claimed:
                merge.ambiguous += 1
                continue
            claimed[spot["id"]] = identifier
            spot.update(osm_attributes(record))
            merge.enriched += 1
            continue

        # Unmatched, so this record is a candidate for publication and has to
        # survive the same two placement tests every DOHMH cafe does. The
        # Overpass bounding box is a rectangle and the city is not, so this is
        # where New Jersey leaves: NYC_BOUNDS first because it is cheap, then
        # the real neighborhood boundaries.
        if not in_new_york_city(latitude, longitude):
            merge.unplaceable += 1
            continue
        area = locate_nta(latitude, longitude, areas)
        if area is None:
            merge.unplaceable += 1
            continue

        # Before publishing it, make sure it is not a cafe the snapshot already
        # has under another spelling.
        neighbours = within(latitude, longitude, grid, OSM_SAME_STOREFRONT_METRES)
        if any(
            not (address_key and identities[spot["id"]].address != address_key)
            for spot in neighbours
        ):
            merge.ambiguous += 1
            continue

        added.append(osm_spot(record, name, latitude, longitude, area))
        merge.added += 1

    return added, merge


def in_new_york_city(latitude: float, longitude: float) -> bool:
    """Whether a point is plausibly in the five boroughs."""
    south, north, west, east = NYC_BOUNDS
    return south <= latitude <= north and west <= longitude <= east


def coordinate(record: dict[str, Any], field: str, limit: float) -> float | None:
    raw = record.get(field)
    if raw is None or raw == "":
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise IngestError(f"Record {spot_id(record)} has a non-numeric {field}: {raw!r}.") from None
    if not math.isfinite(value) or abs(value) > limit:
        raise IngestError(f"Record {spot_id(record)} has an out-of-range {field}: {value!r}.")
    return round(value, COORDINATE_DIGITS)


def haversine_metres(
    latitude: float, longitude: float, other_latitude: float, other_longitude: float
) -> float:
    first, second = math.radians(latitude), math.radians(other_latitude)
    delta_latitude = second - first
    delta_longitude = math.radians(other_longitude - longitude)
    arc = (
        math.sin(delta_latitude / 2) ** 2
        + math.cos(first) * math.cos(second) * math.sin(delta_longitude / 2) ** 2
    )
    return 2 * EARTH_RADIUS_METRES * math.asin(math.sqrt(arc))


def hotspot_points(rows: list[Any]) -> list[tuple[float, float]]:
    """Usable coordinates from the Wi-Fi rows, ignoring ungeocoded ones."""
    points: list[tuple[float, float]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        latitude = coordinate(row, "latitude", 90.0)
        longitude = coordinate(row, "longitude", 180.0)
        if latitude is not None and longitude is not None:
            points.append((latitude, longitude))
    return points


def has_free_wifi(latitude: float, longitude: float, hotspots: list[tuple[float, float]]) -> bool:
    """Whether a free public hotspot sits within :data:`WIFI_RADIUS_METRES`.

    False means no free hotspot is recorded near the spot, which is not the same
    as there being no Wi-Fi: an NYU building has Wi-Fi that needs NYU
    credentials, and the city's dataset has no reason to know about it. The
    field answers "can anyone use Wi-Fi here", which is the question a study
    spot raises.
    """
    # A degree of latitude is about 111 km everywhere, and a degree of longitude
    # at least 78 km at New York's latitude, so this box can only ever be
    # generous. It turns a million haversine calls into a few thousand.
    margin = WIFI_RADIUS_METRES / 78_000.0

    return any(
        abs(spot_latitude - latitude) <= margin
        and abs(spot_longitude - longitude) <= margin
        and haversine_metres(latitude, longitude, spot_latitude, spot_longitude)
        <= WIFI_RADIUS_METRES
        for spot_latitude, spot_longitude in hotspots
    )


def nearest_campus(latitude: float, longitude: float, campuses: list[Campus]) -> str | None:
    """The closest curated campus within ``CAMPUS_RADIUS_METRES``, if any.

    Proximity, not affiliation: see this module's docstring.
    """
    nearby = [
        (haversine_metres(latitude, longitude, campus.latitude, campus.longitude), campus.name)
        for campus in campuses
    ]
    # Sorting on the name too keeps two equidistant campuses from making the
    # snapshot depend on the order upstream happened to return rows in.
    within = sorted(pair for pair in nearby if pair[0] <= CAMPUS_RADIUS_METRES)
    return within[0][1] if within else None


def normalize(
    facilities: list[Any],
    cafes: list[Any],
    names: dict[str, str],
    hotspots: list[Any],
    *,
    areas: list[NtaArea] | None = None,
    outdoor_dining: list[Any] | None = None,
    osm: list[Any] | None = None,
) -> list[dict[str, Any]]:
    """The whole mapping, from raw upstream records to contract records.

    Both registers are normalized here rather than in separate passes so that
    the two derivations that depend on the whole snapshot -- the Wi-Fi
    proximity test and the nearest campus -- are applied once, to everything,
    and cannot drift between sources.

    ``areas``, ``outdoor_dining`` and ``osm`` are keyword-only and serve the
    cafes alone: a caller mapping facilities needs none of them, and most of the
    test suite is exactly that caller. Passing cafes without ``areas`` is an
    error rather than a default, because the fallback would be to drop every
    cafe for want of a borough -- which looks like upstream having no coffee
    shops today.

    ``osm`` is additive and may be empty. Without it the cafes are the DOHMH
    establishments with three unrecorded fields, which is a smaller snapshot
    rather than a wrong one; the OSM records can only add attributes to those
    establishments and publish cafes DOHMH files under another cuisine.
    """
    if cafes and not areas:
        raise IngestError("Mapping cafes needs the NTA boundaries; pass areas=nta_areas(rows).")
    areas = areas or []
    spots: list[dict[str, Any]] = []
    skipped = 0

    for record in facilities:
        if not isinstance(record, dict):
            raise IngestError("An upstream record is not a JSON object.")

        published_category = category(record)
        if published_category is None:
            continue

        name = text(record.get("facname"))
        if name is None:
            raise IngestError(f"Record {spot_id(record)} has no name.")

        latitude = coordinate(record, "latitude", 90.0)
        longitude = coordinate(record, "longitude", 180.0)
        if latitude is None or longitude is None:
            # Nothing can place these on a map, and the model requires both.
            # Upstream ungeocoded rows should not fail a whole import.
            skipped += 1
            continue

        if not in_new_york_city(latitude, longitude):
            # Geocoded, but not to here. Publishing it would put the spot in
            # the wrong place on a map and give it nonsense neighbours.
            warn(f"{spot_id(record)} is at {latitude},{longitude}, outside the city; skipping")
            skipped += 1
            continue

        spots.append(
            {
                "id": spot_id(record),
                "name": title_case(name),
                "category": published_category,
                "address": street_address(record),
                "neighborhood": neighborhood(record, names, spot_id(record)),
                "borough": borough(record),
                "latitude": latitude,
                "longitude": longitude,
                # Filled in below: it depends on the rest of the snapshot.
                "university": None,
                "operator": operator(record),
                "free_public_wifi": False,
                "no_purchase_needed": published_category in NO_PURCHASE_CATEGORIES,
                # Filled in by combine(), which is the only point that sees
                # every published spot including the curated ones.
                "subway_station": None,
                "subway_routes": None,
                "subway_metres": None,
                "subway_step_free": None,
                "nearby_spots": 0,
                # Nothing licenses a library to put tables on the pavement, so
                # no facility can match the seating join. False here is the
                # absence of a licence, which is what the field means
                # everywhere.
                "outdoor_seating": False,
                # OpenStreetMap is read for cafes alone, so these three are
                # unrecorded for every library and campus building. Null rather
                # than false: nobody has said a branch has no indoor seating,
                # which would be a strange thing to say about a library.
                "indoor_seating": None,
                "venue_wifi": None,
                "opening_hours": None,
            }
        )

    if skipped:
        warn(f"skipped {skipped} record(s) without coordinates")

    # Inspections, not establishments: 21,422 rows describe 2,225 coffee shops,
    # so the log is folded down to the most recent inspection of each before
    # anything is mapped.
    inspected = establishments(cafes)
    index = outdoor_dining_index(outdoor_dining or [])

    closed = 0
    unusable = 0
    seated = 0
    # Each DOHMH cafe's name and street address as the OSM join compares them,
    # collected here because this is the last point the raw row is in hand.
    identities: dict[str, CafeIdentity] = {}
    dohmh_cafes: list[dict[str, Any]] = []
    for camis, record in inspected.items():
        if CLOSURE_ACTION.search(text(record.get("action")) or ""):
            # The health department closed it at its most recent inspection and
            # has not recorded a re-opening since. Publishing it as somewhere to
            # go would send a student to a locked door.
            closed += 1
            continue
        spot = cafe_spot(camis, record, areas, index)
        if spot is None:
            unusable += 1
            continue
        if spot["outdoor_seating"]:
            seated += 1
        identities[spot["id"]] = CafeIdentity(
            name=match_key(record.get("dba")),
            address=match_key(
                f"{text(record.get('building')) or ''} {text(record.get('street')) or ''}"
            ),
        )
        dohmh_cafes.append(spot)

    if closed:
        warn(f"skipped {closed} establishment(s) closed at their most recent inspection")
    if unusable:
        warn(f"skipped {unusable} establishment(s) that could not be placed")
    print(
        f"ingest: {len(inspected)} coffee/tea establishments from {len(cafes)} inspection rows; "
        f"{seated} matched a sidewalk licence",
        file=sys.stderr,
    )

    # Additive: this enriches the DOHMH cafes in place and returns the ones OSM
    # alone knows about. Nothing above is dropped or changed by it.
    osm_added, merge = merge_osm_cafes(dohmh_cafes, identities, osm or [], areas)
    spots.extend(dohmh_cafes)
    spots.extend(osm_added)
    if osm:
        print(
            f"ingest: {len(osm)} OpenStreetMap cafes: {merge.enriched} enriched a DOHMH "
            f"establishment, {merge.added} published as new spots, {merge.ambiguous} skipped as "
            f"ambiguous, {merge.unplaceable} outside the city",
            file=sys.stderr,
        )

    points = hotspot_points(hotspots)
    for spot in spots:
        spot["free_public_wifi"] = has_free_wifi(spot["latitude"], spot["longitude"], points)

    campuses = [
        Campus(spot["name"], spot["latitude"], spot["longitude"])
        for spot in spots
        if spot["category"] == CAMPUS_CATEGORY
    ]
    for spot in spots:
        if spot["category"] == CAMPUS_CATEGORY:
            spot["university"] = spot["name"]
        elif spot["category"] == CAFE_CATEGORY:
            # Cafes are third places in their own right, not somewhere you
            # reach through a campus, so the field stays null however close one
            # happens to be. A library beside a campus is plausibly *its*
            # library; the cafe on the same corner is just a cafe.
            #
            # The measurement that settled it: 41% of cafes picked up a label
            # here, and tightening the radius made it worse rather than better.
            # FacDB stores one point per institution whatever its size, so
            # Columbia's whole campus is a single coordinate and its nearest
            # cafe is 181 m away, while a school occupying one floor has one at
            # 67 m. Any radius strips the universities students attend before
            # it strips the vocational schools nobody is looking for.
            spot["university"] = None
        else:
            spot["university"] = nearest_campus(spot["latitude"], spot["longitude"], campuses)

    # Campus records anchor the derivation above and are then dropped rather
    # than published. A FacDB campus is an administrative point for an
    # institution, not a room: "Daemen University-Brooklyn Branch" is a
    # registration, and nobody can sit down in it. The application lists places
    # a person can actually go, and access to a campus is restricted anyway.
    #
    # They still have to be built, because the "near which campus" label on the
    # libraries is derived from exactly these coordinates. The curated NYU
    # buildings are the campus study space the snapshot does publish, and those
    # were recorded by hand from public building information.
    published = [spot for spot in spots if spot["category"] != CAMPUS_CATEGORY]

    validate(published)
    # Identifiers rather than names: a renamed facility then moves one line of
    # the snapshot instead of shifting every record after it.
    return sorted(published, key=lambda spot: spot["id"])


def subway_stations(path: Path = SUBWAY_PATH) -> list[dict[str, Any]]:
    """The committed station list, or an empty list when it has not been built."""
    if not path.exists():
        warn(f"no {path.name}; spots will publish no subway. Run `just ingest-subway`.")
        return []
    stations = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(stations, list):
        raise IngestError(f"{path} must contain a JSON array of stations.")
    return stations


def assign_nearby(spots: list[dict[str, Any]]) -> None:
    """Count each spot's neighbours within :data:`NEARBY_RADIUS_METRES`, in place.

    This is the only thing in the snapshot that says anything about what a
    block is like, and it is worth being precise about what it does and does
    not mean. It counts *other study spots*, not people. A café on a dense
    stretch may be empty and an isolated library may be packed; nothing here
    knows. What it does support is the question a reader can act on -- how busy
    the surrounding streets are, and whether there is anywhere else to go if
    this place is full.

    Bucketed onto a coarse grid first, so this is 3,772 lookups of a few
    neighbours rather than 3,772 squared comparisons.
    """
    grid: dict[tuple[float, float], list[dict[str, Any]]] = {}
    for spot in spots:
        key = (round(spot["latitude"], 2), round(spot["longitude"], 2))
        grid.setdefault(key, []).append(spot)

    # A hundredth of a degree is about 1.1 km north-south and 850 m east-west
    # in New York, so the neighbouring cells comfortably cover the radius.
    offsets = (-0.01, 0.0, 0.01)
    for spot in spots:
        latitude, longitude = spot["latitude"], spot["longitude"]
        count = 0
        for delta_lat in offsets:
            for delta_lon in offsets:
                cell = (round(latitude + delta_lat, 2), round(longitude + delta_lon, 2))
                for other in grid.get(cell, ()):
                    if other["id"] == spot["id"]:
                        continue
                    if (
                        haversine_metres(latitude, longitude, other["latitude"], other["longitude"])
                        <= NEARBY_RADIUS_METRES
                    ):
                        count += 1
        spot["nearby_spots"] = count


def assign_subway(spots: list[dict[str, Any]], stations: list[dict[str, Any]]) -> None:
    """Give every spot its nearest station, in place.

    Derived here rather than in the browser or the frontend build, for the
    reason `no_purchase_needed` had to learn: the result cards are rendered
    from the API and the detail pages from the snapshot, so anything computed
    in one of those places is missing from the other. The importer is the only
    point both of them read from.

    Measured to the station rather than to an entrance. The MTA publishes
    entrances too and they would be closer to the truth, but a station can span
    two avenues and an entrance list invites a precision the rest of this
    snapshot does not have: the spot coordinates are themselves building
    centroids.
    """
    for spot in spots:
        nearest: tuple[float, dict[str, Any]] | None = None
        for station in stations:
            metres = haversine_metres(
                spot["latitude"], spot["longitude"], station["latitude"], station["longitude"]
            )
            if metres <= SUBWAY_RADIUS_METRES and (nearest is None or metres < nearest[0]):
                nearest = (metres, station)

        if nearest is None:
            spot["subway_station"] = None
            spot["subway_routes"] = None
            spot["subway_metres"] = None
            spot["subway_step_free"] = None
            continue

        metres, station = nearest
        spot["subway_station"] = station["name"]
        # Space-joined, the way the MTA publishes it and the way a sign reads.
        spot["subway_routes"] = " ".join(station["routes"])
        spot["subway_metres"] = round(metres)
        spot["subway_step_free"] = station["step_free"]


def curated_spots(path: Path = CURATED_PATH) -> list[dict[str, Any]]:
    """Read the hand-maintained building records.

    These arrive already in the shared contract rather than in an upstream
    shape, so the work here is checking that they still match it. A hand-edited
    file is exactly where a typo or a field outside the contract appears, and
    finding it here names the record instead of failing at load time.
    """
    if not path.exists():
        raise IngestError(f"No curated building list at {path}.")

    records = json.loads(path.read_text("utf-8"))
    if not isinstance(records, list):
        raise IngestError(f"{path} must contain a JSON array of study spots.")

    spots: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise IngestError(f"Curated record {index} is not a JSON object.")

        name = record.get("id", index)
        missing = [field for field in CONTRACT_FIELDS if field not in record]
        if missing:
            raise IngestError(f"Curated record {name!r} is missing {missing}.")

        extra = sorted(set(record) - set(CONTRACT_FIELDS))
        if extra:
            raise IngestError(f"Curated record {name!r} has fields outside the contract: {extra}.")

        # Rebuilt in contract order: validate() compares the key order itself,
        # and a hand-edited file has no reason to preserve it.
        spots.append({field: record[field] for field in CONTRACT_FIELDS})

    return spots


def drop_curated_duplicates(
    spots: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[tuple[str, str]]]:
    """Drop open-data records that are really the curated building beside them.

    FacDB registers "New York University Libraries" as an academic library at
    Bobst's coordinates, 12 m from the curated ``nyu:bobst-library``. It is the
    same building twice: a search for "bobst" returned both, because the search
    vector includes the address and FacDB wrote the *building name* where a
    street belongs. The curated record wins -- it has the real street address,
    and the right university, where FacDB says "LIU-New York University
    Campus", which is Long Island University.

    Three conditions, and every one of them is load-bearing:

    **Same category.** This is what protects the cafes. Nine non-curated
    records sit within 60 m of a curated building and all nine are genuine
    separate study spots -- Peet's Coffee @ NYU is 10 m from the Kimmel Center,
    Blank Street Coffee is 26 m from Rogers Hall, The Uncommons 24 m from the
    Global Center, Think Coffee 37 m from Courant. They are cafes *inside or
    beside* the building. A proximity-only rule would delete all nine to fix
    one duplicate.

    **Within :data:`CURATED_DUPLICATE_METRES`.** Two records of one category
    across the street from each other are two places.

    **No house number in the address.** This is the condition that is easy to
    leave out, and leaving it out costs a real record. *Two* academic libraries
    sit within 50 m of Bobst, not one: the generic FacDB row above, and "NYU
    Tamiment Library" at 17 m -- the Tamiment Library and Robert F. Wagner
    Labor Archives, a named special collection on Bobst's tenth floor. It
    publishes its own street address, "70 Washington Square South". It is a
    library someone might search for by name and it is not a duplicate of
    anything.

    So the test is not "is it near the building" but "does it claim an address
    of its own". A row that cannot say what street it is on, sitting on top of
    a curated building of the same kind, has recorded that building. A row with
    a street address is asserting a place, and is kept even when the street is
    the curated record's own.

    Returns the surviving spots and what was dropped, as ``(dropped, kept)``
    name pairs, so the importer can report it rather than deleting records
    quietly.
    """
    curated = [spot for spot in spots if spot["id"].startswith(f"{CURATED_PREFIX}:")]
    if not curated:
        return spots, []

    dropped: dict[str, tuple[str, str]] = {}
    for spot in spots:
        if spot["id"].startswith(f"{CURATED_PREFIX}:"):
            continue
        if HOUSE_NUMBER.match(spot["address"] or ""):
            continue
        for building in curated:
            if building["category"] != spot["category"]:
                continue
            metres = haversine_metres(
                spot["latitude"], spot["longitude"], building["latitude"], building["longitude"]
            )
            if metres <= CURATED_DUPLICATE_METRES:
                dropped[spot["id"]] = (spot["name"], building["name"])
                break

    kept = [spot for spot in spots if spot["id"] not in dropped]
    return kept, list(dropped.values())


def combine(
    facilities: list[dict[str, Any]],
    curated: list[dict[str, Any]],
    stations: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Merge the curated buildings over the open-data records.

    A curated entry wins an identifier collision, because it was written by
    someone who checked the building and the open-data row was not. Collisions
    should not happen -- the two sources use different identifier prefixes --
    but an importer that silently kept the wrong one would be worse than one
    that prefers the deliberate record.

    The curated entries keep the ``university`` they were given. For an
    open-data record that field is the nearest campus within 500 m; for these it
    is the institution whose building it is, which is the stronger claim the
    contract allows for a campus record.

    A curated entry also wins against an open-data record that is the same
    building under another name, which is a different thing from an identifier
    collision and is what :func:`drop_curated_duplicates` resolves.
    """
    merged = {spot["id"]: spot for spot in facilities}
    merged.update({spot["id"]: spot for spot in curated})

    spots = sorted(merged.values(), key=lambda spot: spot["id"])

    # Before the two derivations below rather than after: a record about to be
    # dropped should not be counted as somebody else's neighbour.
    spots, duplicates = drop_curated_duplicates(spots)
    for name, building in duplicates:
        warn(f"dropped {name!r}; it is the curated {building!r} under another name")

    # After merging rather than inside normalize(), because the curated records
    # never pass through it: this is the only point that sees every published
    # spot, and a hand-maintained station per building would go stale.
    assign_subway(spots, stations if stations is not None else [])
    assign_nearby(spots)
    validate(spots)
    return spots


def validate(spots: list[dict[str, Any]]) -> None:
    """Refuse a snapshot ``load_spots`` would reject.

    The loader validates every record too, but it runs at deployment time and
    inside a Lambda function. Failing here points at the importer instead.
    """
    seen: set[str] = set()
    for spot in spots:
        if tuple(spot) != CONTRACT_FIELDS:
            raise IngestError(
                f"Record {spot['id']} does not match the shared contract: {list(spot)}."
            )
        if spot["id"] in seen:
            # Two records with one identifier means uid is not the identity it
            # is being used as, and the load would quietly keep one of them.
            raise IngestError(f"Duplicate identifier {spot['id']!r}.")
        seen.add(spot["id"])
        for field in ("name", "category", "borough"):
            if not isinstance(spot[field], str) or not spot[field]:
                raise IngestError(f"Record {spot['id']} has an empty {field}.")
        for field in ("address", "neighborhood", "university"):
            if spot[field] is not None and not str(spot[field]).strip():
                raise IngestError(f"Record {spot['id']} has a blank {field}; it should be null.")


def write_snapshot(path: Path, spots: list[dict[str, Any]]) -> None:
    # ensure_ascii=False keeps "García" readable in the diff; the loader and the
    # API are UTF-8 throughout.
    path.write_text(json.dumps(spots, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Normalize NYC Open Data into the study-spot snapshot."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Where to write the snapshot (default: %(default)s).",
    )
    parser.add_argument(
        "--fixtures",
        type=Path,
        nargs="?",
        const=DEFAULT_FIXTURES,
        default=None,
        help=(
            "Read the committed upstream sample from this directory instead of the network "
            f"(default when the flag is given: {DEFAULT_FIXTURES})."
        ),
    )
    options = parser.parse_args(argv)

    try:
        facilities, cafes, outdoor_dining, neighborhoods, hotspots = read_sources(options.fixtures)
        spots = combine(
            normalize(
                facilities,
                cafes,
                neighborhood_names(neighborhoods),
                hotspots,
                areas=nta_areas(neighborhoods),
                outdoor_dining=outdoor_dining,
                osm=osm_source(options.fixtures),
            ),
            curated_spots(),
            subway_stations(),
        )
    except IngestError as error:
        warn(str(error))
        return 1

    write_snapshot(options.output, spots)
    counts = Counter(spot["category"] for spot in spots)
    summary = ", ".join(f"{count} {name}" for name, count in sorted(counts.items()))
    wifi = sum(1 for spot in spots if spot["free_public_wifi"])
    outdoor = sum(1 for spot in spots if spot["outdoor_seating"])
    print(
        f"wrote {len(spots)} spots ({summary}; {wifi} with free public wifi; "
        f"{outdoor} with outdoor seating) to {options.output}"
    )
    # Reported three ways rather than as one total, because the whole reason
    # these three fields exist is that "no" and "unrecorded" are different
    # answers. A single "how many carry it" would hide that.
    for field in OSM_FIELDS:
        values = [spot[field] for spot in spots]
        if field == "opening_hours":
            print(f"  {field}: {sum(1 for value in values if value)} recorded")
            continue
        print(
            f"  {field}: {values.count(True)} true, {values.count(False)} false, "
            f"{values.count(None)} unrecorded"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
