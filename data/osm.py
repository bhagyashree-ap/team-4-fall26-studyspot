"""Fetch the OpenStreetMap cafes that the importer merges over DOHMH.

.. code-block:: text

    Overpass API -> osm.py -> osm_cafes.json

Run it through just::

    just ingest-osm

Separate from ``ingest.py`` for the same reasons ``subway.py`` is: the records
come from somewhere else entirely -- the Overpass API rather than the city's
Socrata portal -- and one request to Overpass takes about 45 seconds and is
rate-limited by a volunteer-run service, which is not something to put in the
path of every ``just ingest``.

Like ``subway_stations.json``, the output is committed. A checkout can rebuild
the whole snapshot without reaching Overpass, which matters more here than it
does for the subway: Overpass is free infrastructure maintained by volunteers,
it sheds load by returning 429 and 504 under pressure, and a build that fails
because somebody else is running a heavy query is not a build worth having.

Why OpenStreetMap, when DOHMH already supplies the cafes
--------------------------------------------------------

This is **additive**. DOHMH stays the spine: it is a register of establishments
the city inspects, so it is the best evidence available that a business exists
and where. OSM is read for the one thing DOHMH cannot do and for three
attributes DOHMH does not carry.

What DOHMH cannot do is classify a place by what it *is*. ``cuisine_description``
is a food-safety code chosen from a fixed list, one value per establishment, and
a cafe that sells sandwiches can be filed under something else entirely. Caffe
Reggio has been on MacDougal Street since 1927 and DOHMH files it as
``Italian``, so filtering on ``Coffee/Tea`` loses it. Precision rose when the
category moved onto DOHMH and recall fell; this is the recall.

``amenity=cafe`` in OSM is a human judgement about what the place is, which is
the question the category asks. It is also not a name match, which is the other
thing that was considered and rejected: a name says nothing about whether
somewhere is a study spot, and matching cafe words in the name pulls in every
deli called "Cafe Metro". OSM does not have that problem, because it tags a
deli as ``shop=deli`` -- of the 3,011 ``amenity=cafe`` records in the city, 15
have "deli", "bodega" or "grocery" anywhere in the name.

What it supplies, measured against the live API
-----------------------------------------------

For the NYC bounding box, nodes and ways:

=================  =====  =====
tag                count      %
=================  =====  =====
``amenity=cafe``   3,011   100%
``opening_hours``  1,566    52%
``outdoor_seating``  890    30%
``internet_access``  506    17%
``indoor_seating``   169     6%
=================  =====  =====

Only three of those are read, and ``outdoor_seating`` is deliberately not one of
them. The snapshot already has a field by that name and it means something
narrower and checkable -- a Dining Out NYC sidewalk licence matching this
establishment's name and address -- so filling it from a different source with a
different meaning would quietly change what the field claims. OSM's version
also arrives as nineteen distinct values, from ``sidewalk;street`` to ``bench``,
which is not a boolean.

What is published instead of what arrives
-----------------------------------------

Three fields, each with three states: true, false, and *unrecorded*. The
difference matters enough to be the point of reading OSM at all. ``internet_access
= no`` is somebody who went and looked: it is a trustworthy negative, unlike
``free_public_wifi = false``, which only ever meant "no hotspot the city
publishes sits within 25 m". Collapsing the unrecorded 83% into ``false`` would
turn an absence of evidence into a claim, which is the one thing this snapshot
tries not to do.

Normalized rather than cached raw, which is how ``subway_stations.json`` is
handled too. The raw Overpass payload is about 2.5 MB of tags nothing reads --
``wheelchair``, ``takeaway``, ``smoking``, the lot -- and committing it would
make every refresh an unreviewable diff. The committed file carries the nine
values the importer uses, sorted, so an unchanged upstream produces a
byte-identical file.

What this does not establish
----------------------------

OSM is contributed data, and an ``amenity=cafe`` node is somebody's judgement
that was true when they made it. A closed cafe can sit in OSM for years, which
is the opposite of DOHMH's failure mode (an inspection log knows about closures
and knows nothing about what a place sells). Nothing here reconciles the two:
a record only in OSM is published on OSM's word alone.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
DEFAULT_OUTPUT = HERE / "osm_cafes.json"

#: The main Overpass instance. Free, volunteer-run, and rate-limited per client.
OVERPASS_URL = "https://overpass-api.de/api/interpreter"

#: The five boroughs, as ``(south, west, north, east)``.
#:
#: Overpass orders a bounding box differently from :data:`ingest.NYC_BOUNDS`,
#: which is ``(south, north, west, east)``. The same box, reordered --
#: ``test_osm.py`` asserts that, because two definitions of where New York is
#: have drifted apart on this project before.
#:
#: This is a query filter and not a guarantee: the importer re-tests every
#: record against ``in_new_york_city()`` and then against the real neighborhood
#: boundaries, which is what actually keeps New Jersey out. The box reaches into
#: Essex County and picks up the cafe at Turtle Back Zoo in West Orange.
NYC_BBOX = (40.47, -74.30, 40.93, -73.68)

#: Nodes and ways both, because a cafe large enough to be a building is a way.
#:
#: ``out center tags`` gives a way its bounding-box centre rather than its
#: outline: the rest of the snapshot is building centroids, so a polygon would
#: be a precision nothing else here has. Relations are not asked for -- there
#: are none tagged ``amenity=cafe`` in the city, and a relation has no centre
#: this would know what to do with.
QUERY = """\
[out:json][timeout:{timeout}];
(
  node["amenity"="cafe"]({south},{west},{north},{east});
  way["amenity"="cafe"]({south},{west},{north},{east});
);
out center tags;
"""

#: Generous on purpose. The city-wide query takes about 45 seconds when Overpass
#: is idle and several minutes when it is not, and a client that gives up early
#: leaves the server doing the work anyway.
HTTP_TIMEOUT_SECONDS = 300

#: What the query asks Overpass to allow itself, which has to be at least as
#: long as the client is prepared to wait or the server quits first.
QUERY_TIMEOUT_SECONDS = 280

#: Overpass asks for identifiable traffic and blocks clients it cannot name.
USER_AGENT = "StudySpot-ingest/1.0 (+https://github.com/gcivil-nyu-org/team-4-fall26)"

#: Below this, something is wrong upstream rather than in New York.
#:
#: 3,011 records today. A query that comes back with a handful is Overpass
#: having served a partial result or the tag having been renamed, and an
#: importer that accepted it would publish a snapshot missing most of its cafes
#: without saying so. Failing loudly is the whole point: the committed file is
#: still there, and a build that uses yesterday's cafes is better than one that
#: silently drops two thousand of them.
MINIMUM_CAFES = 2000

#: ``internet_access`` as a claim about the venue's own Wi-Fi.
#:
#: ``wlan`` is the specific value and the common one (348 of 506); ``yes`` is
#: generic internet access, which for a cafe in 2026 is Wi-Fi (100); ``wifi`` is
#: a non-standard spelling that occurs. ``no`` is the negative this field exists
#: for.
#:
#: Everything absent from this table is **unrecorded rather than false**, and
#: that includes the values that mean something real: ``wired`` is an ethernet
#: port and ``terminal`` is a public computer, and neither says whether there is
#: also Wi-Fi. A mapping table rather than a truthiness test, so a value nobody
#: has thought about reads as unknown instead of as a claim.
INTERNET_ACCESS = {
    "wlan": True,
    "yes": True,
    "wifi": True,
    "no": False,
}

#: ``indoor_seating``, which OSM records as a plain yes or no.
#:
#: 150 yes and 19 no in the city, and nothing else. The same rule applies:
#: anything not in here is unrecorded.
INDOOR_SEATING = {
    "yes": True,
    "no": False,
}

#: What OSM uses to separate several values in one tag.
#:
#: Semicolon is the documented convention. The comma is here because one record
#: in the city carries ``internet_access = "yes, wifi"``, which is a person
#: writing prose into a tag; splitting on both reads it as the two values it
#: plainly is rather than as one unrecognized string.
TAG_SEPARATORS = ";,"


class OsmError(RuntimeError):
    """Raised when Overpass cannot be turned into a usable cafe list."""


def overpass_query(timeout: int = QUERY_TIMEOUT_SECONDS) -> str:
    south, west, north, east = NYC_BBOX
    return QUERY.format(timeout=timeout, south=south, west=west, north=north, east=east)


def fetch(url: str = OVERPASS_URL) -> list[Any]:
    """Every ``amenity=cafe`` in the city, in one request.

    POST rather than GET: the query goes in the body, which is what Overpass
    documents and what keeps a long query out of a URL. There is no paging --
    Overpass answers a query whole or not at all.
    """
    request = urllib.request.Request(
        url,
        data=urllib.parse.urlencode({"data": overpass_query()}).encode("utf-8"),
        headers={
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as error:
        if error.code in (429, 504):
            # Overpass's two ways of saying "not now": 429 when this client has
            # used its share of the slot pool, 504 when the server is loaded
            # enough to give up mid-query. Both are worth naming, because the
            # answer to each is to wait rather than to change the query.
            raise OsmError(
                f"Overpass answered HTTP {error.code}, which means it is busy rather than "
                f"that the query is wrong. Wait a few minutes and run `just ingest-osm` "
                f"again; {DEFAULT_OUTPUT.name} is committed, so nothing is blocked meanwhile."
            ) from error
        detail = error.read(200).decode("utf-8", "replace").strip()
        raise OsmError(f"Overpass answered HTTP {error.code}: {detail}") from error
    except urllib.error.URLError as error:
        raise OsmError(f"Could not reach {url}: {error.reason}") from error
    except json.JSONDecodeError as error:
        # Overpass reports a syntax error in the query as an HTML page with a
        # 200, so a body that is not JSON is a bug here and not a server fault.
        raise OsmError(f"{url} did not answer with JSON: {error}") from error

    if not isinstance(payload, dict):
        raise OsmError(f"{url} answered with {type(payload).__name__}, not an object.")
    elements = payload.get("elements")
    if not isinstance(elements, list):
        raise OsmError(f"{url} answered without an elements array.")
    return elements


def element_id(element: dict[str, Any]) -> str | None:
    """OSM's identity for one element, as ``n123`` or ``w456``.

    An OSM identifier is only unique within its element type, so the type has to
    be part of it: a node and a way may both be numbered 3506087030. Written as
    a letter and the number rather than OSM's own ``node/3506087030`` because
    this becomes part of a spot identifier, and a spot identifier becomes a URL
    path segment -- ``/spots/osm:node/3506087030`` would be two segments and a
    404.
    """
    kind = {"node": "n", "way": "w"}.get(str(element.get("type")))
    identifier = element.get("id")
    if kind is None or not isinstance(identifier, int):
        return None
    return f"{kind}{identifier}"


def centre(element: dict[str, Any]) -> tuple[float, float] | None:
    """Where the element is: a node's own point, or a way's bounding-box centre."""
    if element.get("type") == "node":
        latitude, longitude = element.get("lat"), element.get("lon")
    else:
        middle = element.get("center")
        if not isinstance(middle, dict):
            return None
        latitude, longitude = middle.get("lat"), middle.get("lon")

    try:
        return float(latitude), float(longitude)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def tag_values(value: Any) -> list[str]:
    """One tag's values, lower-cased, however many a contributor packed into it."""
    if not isinstance(value, str):
        return []
    separated = value
    for separator in TAG_SEPARATORS:
        separated = separated.replace(separator, "\n")
    return [part.strip().lower() for part in separated.split("\n") if part.strip()]


def three_state(value: Any, vocabulary: dict[str, bool]) -> bool | None:
    """``True``, ``False``, or ``None`` for a tag nobody has recorded.

    ``None`` is also what an unrecognized value gives, and what a tag carrying
    two values that disagree gives. Both are genuinely unknown: a contributor
    writing something this does not understand is not evidence either way, and
    choosing one of two contradictory values would be inventing an answer.
    """
    known = {vocabulary[part] for part in tag_values(value) if part in vocabulary}
    if len(known) != 1:
        return None
    return known.pop()


def text(value: Any) -> str | None:
    """A trimmed string, or ``None`` for anything a contributor left blank."""
    if not isinstance(value, str):
        return None
    collapsed = " ".join(value.split())
    return collapsed or None


def normalize(elements: list[Any]) -> list[dict[str, Any]]:
    """Map the Overpass elements onto the handful of values the importer reads.

    A record with no name or no coordinates is dropped rather than published:
    33 ``amenity=cafe`` records in the city have no ``name``, and the snapshot
    requires one. They are counted so the number is visible rather than
    silently absent.

    Coordinates are left unrounded here. ``ingest.py`` rounds every coordinate
    it publishes to six places, and rounding twice in two modules is how the two
    stop agreeing.
    """
    cafes: list[dict[str, Any]] = []
    unnamed = 0
    unplaced = 0
    for element in elements:
        if not isinstance(element, dict):
            raise OsmError("An Overpass element is not a JSON object.")

        identifier = element_id(element)
        if identifier is None:
            raise OsmError(f"An Overpass element has no usable type and id: {element!r}.")

        tags = element.get("tags")
        tags = tags if isinstance(tags, dict) else {}
        name = text(tags.get("name"))
        point = centre(element)
        if name is None:
            unnamed += 1
            continue
        if point is None:
            unplaced += 1
            continue

        latitude, longitude = point
        cafes.append(
            {
                "id": identifier,
                "name": name,
                "latitude": latitude,
                "longitude": longitude,
                # Kept apart rather than joined into one string. The importer
                # matches on a normalized house number and street, and it
                # already has to take DOHMH's two columns apart to do it.
                "house_number": text(tags.get("addr:housenumber")),
                "street": text(tags.get("addr:street")),
                # Not matched on -- DOHMH's zip and OSM's disagree often enough
                # that requiring them to agree would cost real matches. It is
                # here so that a cafe only OSM knows about publishes an address
                # in the same shape as every other cafe's.
                "postcode": text(tags.get("addr:postcode")),
                "indoor_seating": three_state(tags.get("indoor_seating"), INDOOR_SEATING),
                "venue_wifi": three_state(tags.get("internet_access"), INTERNET_ACCESS),
                # OSM's own syntax, stored as written: "Mo-Fr 07:00-19:00;
                # Sa-Su 08:00-18:00". Not parsed, and deliberately not turned
                # into an "open now" -- that needs a timezone and the public
                # holiday calendar the syntax can refer to, and getting it
                # wrong sends somebody to a closed door.
                "opening_hours": text(tags.get("opening_hours")),
            }
        )

    if len(cafes) < MINIMUM_CAFES:
        raise OsmError(
            f"Overpass returned {len(cafes)} usable cafes, fewer than the {MINIMUM_CAFES} "
            "this query has always produced. Refusing to publish what looks like a partial "
            "result; the committed file is still good."
        )
    if unnamed:
        print(f"osm: {unnamed} cafe(s) have no name and cannot be published", file=sys.stderr)
    if unplaced:
        print(f"osm: {unplaced} cafe(s) have no coordinates", file=sys.stderr)

    # Sorted so that an unchanged upstream produces a byte-identical file and
    # the diff shows what actually moved.
    return sorted(cafes, key=lambda cafe: cafe["id"])


def main(argv: list[str] | None = None) -> int:
    output = Path(argv[0]) if argv else DEFAULT_OUTPUT
    try:
        cafes = normalize(fetch())
    except OsmError as error:
        print(f"osm: {error}", file=sys.stderr)
        return 1

    output.write_text(json.dumps(cafes, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    hours = sum(1 for cafe in cafes if cafe["opening_hours"])
    wifi = sum(1 for cafe in cafes if cafe["venue_wifi"] is not None)
    indoor = sum(1 for cafe in cafes if cafe["indoor_seating"] is not None)
    print(
        f"wrote {len(cafes)} cafes ({hours} with opening hours, {wifi} with recorded "
        f"venue wifi, {indoor} with recorded indoor seating) to {output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
