# HTTP API

The API is available directly at `http://localhost:7501` and through the frontend proxy under `http://localhost:7500/api`. Deployments publish it under `/api`, and both edges strip that prefix before the request reaches the application, so the routes below are the same everywhere.

No route has a trailing slash, and the application does not redirect one onto the other: `/spots/` is a 404 rather than a 301 to `/spots`.

## Implemented routes

| Route | Purpose |
|---|---|
| `GET /health/live` | Reports whether the API process can serve requests. It intentionally does not contact Postgres. |
| `GET /spots` | Returns a filtered, paginated page of study spots. |
| `GET /spots/{id}` | Returns one study spot. |

`GET /health/live` returns:

```json
{
  "status": "ok"
}
```

## Study-spot summary

```json
{
  "id": "facdb:eec118768e15a5e03d3354abda7b00da",
  "name": "125th Street Library",
  "category": "public_library",
  "address": "224 East 125 Street, New York, NY 10035",
  "neighborhood": "East Harlem (North)",
  "borough": "Manhattan",
  "latitude": 40.803027,
  "longitude": -73.934853,
  "university": "Touro University - Harlem",
  "operator": "New York Public Library",
  "free_public_wifi": true,
  "no_purchase_needed": true,
  "subway_station": "125 St",
  "subway_routes": "4 5 6",
  "subway_metres": 180,
  "subway_step_free": "full",
  "nearby_spots": 23,
  "outdoor_seating": false,
  "indoor_seating": null,
  "venue_wifi": null,
  "opening_hours": null
}
```

The records represent public third places — today the libraries of the city's facilities database, the coffee shops of the health department's inspection register, the cafés OpenStreetMap contributors have mapped, and a curated list of NYU campus buildings. They are candidate gathering and study locations; the API must not imply that unverified amenities are available. This response shape belongs to the shared contract. Changes require review from frontend, API, data, and search owners.

`category` currently takes one of `cafe`, `public_library`, `special_library`, `academic_library` and `university_building`.

`public_library` and `special_library` are kept apart because the difference is the one a reader cares about: a branch of NYPL, BPL or QPL is somewhere anyone can walk into, while a special library is an institutional collection — a club's, a society's, a hospital's — and many are open by appointment or to members only.

`university_building` is a campus building a student can work in. The city's facilities database registers institutions and administrative points rather than buildings, so these come from the curated list in `data/nyu_buildings.json` and all carry the `nyu:` identifier prefix. The institution records themselves are *not* published: an administrative point is not a room, and campus access is restricted. They are read only to anchor the `university` label.

`cafe` comes from two sources read together: the health department's own `Coffee/Tea` cuisine classification, and OpenStreetMap's `amenity=cafe`. See [Data and search](data-and-search.md). The health department decides which establishments exist and where; OpenStreetMap adds the three attributes below and the cafés the health department files under some other cuisine — Caffe Reggio, on MacDougal Street since 1927, is recorded as `Italian` and so is in one source and not the other. It used to come from the outdoor-dining licence register, which published any business holding a sidewalk licence as a café — bars, pizzerias and restaurants among them — and missed every indoor-only coffee shop. The API does not constrain the value: the vocabulary belongs to the importer, and pinning it in the serving schema would put every category change through a migration.

`nearby_spots` is how many other study spots are within 400 m, about a five-minute walk. **It counts places, not people.** A café on a dense stretch may be empty and an isolated library may be packed; nothing in open data knows. What it supports is how lively the surrounding block is, and whether there is anywhere else to go if this one is full. The browser bands it into Quiet, Moderate and Busy at 0 and 10, chosen from the real distribution — the median by borough is Manhattan 32, Brooklyn 9, Queens 6, Bronx 1, Staten Island 2 — and always shows the count beside the word, because a label you can check is a different thing from one you have to trust.

`subway_station`, `subway_routes`, `subway_metres` and `subway_step_free` are the nearest station within 1.2 km, derived by the importer from the MTA's own list. All four are null together — 285 of 3,772 spots have none that close, mostly on Staten Island where the railway is not the subway. The distance is straight-line rather than walking, `routes` is space separated as the MTA publishes it, and `step_free` keeps their three states: `full`, `none`, and `partial` for a platform reachable going one way and not the other.

`no_purchase_needed` is true where sitting down costs nothing — every library and every campus building, and no café. It answers the question a reader actually has, which no single category answers, and **it is about money rather than entry**: a campus building is free and still wants the university's credentials, and a special library may be open only by appointment.

Derived by the importer from the category and stored, as `free_public_wifi` and `university` are. It was briefly computed in the serializer instead, on the argument that a column would be a copy able to drift from the category beside it; prerendering the detail pages disproved that, because those are built from `data/spots.json`, where the field did not exist, and every library's page said a purchase was expected. The snapshot is regenerated as a unit and cannot drift from itself.

`NO_PURCHASE_CATEGORIES` in `data/ingest.py` is the single definition, beside the vocabulary it describes, and it is an allowlist so that a category added there is never silently published as free.

`outdoor_seating` is true when a current Dining Out NYC sidewalk licence matches the establishment's name *and* street address. **False means no licence matched, not that there is nowhere to sit outside.** The join is strict on purpose: matching on address alone would credit a café with the licence of whichever other business shares its building, and in the live data 28 cafés share a street address with a licence held under a different name — "787 Coffee" at 100 Lexington Ave with "Bhatti Indian Grill", "Joe Coffee" at 405 W 23 St with "Henry & The Lions". A café missing its licence reads as a false; a café credited with someone else's would be a false statement about a real business. Only cafés can carry it, because nothing licenses a library to put tables on the pavement. There is no filter on it — it is an attribute the API reports rather than one it narrows on, which is also why it has no index. `free_public_wifi` is true when a free public Wi-Fi hotspot the city publishes
sits within 25 m, derived from `yjub-udmw`. False means none is recorded, which
is not the same as there being no Wi-Fi: a campus building's network needs the
university's credentials, and the city has no reason to know about it. The field
answers whether *anyone* can use Wi-Fi there. `borough` is one of the five
borough names and the database refuses any other. `neighborhood` is the 2020 Neighborhood Tabulation Area name and is `null` when NYC Open Data does not place the record in one.

### The three fields where `null` is an answer

`indoor_seating`, `venue_wifi` and `opening_hours` come from OpenStreetMap, and they are the only three fields in the contract where `null` means *nobody has recorded this* rather than *this record has no such thing*. **A consumer must not read `null` as `false`.** Everywhere else in this contract a null is an absence of the thing — a café has no operator, a spot with no station inside 1.2 km has no station — and treating it as a negative is harmless. Here it is the difference between "somebody went and looked and there is no Wi-Fi" and "nobody has said", and the whole reason the source is read is to be able to tell those apart.

`venue_wifi` is Wi-Fi the venue itself provides, as recorded by a contributor. **It is a different claim from `free_public_wifi` and the two must not be merged or shown as one.** `free_public_wifi` is a hotspot *the city publishes* within 25 m of the point, which is usually a library's own and occasionally a LinkNYC kiosk on the pavement; a café can easily have its own Wi-Fi and no city hotspot anywhere near it, and a library the reverse. Their falses are also worth different amounts: a false here is a trustworthy negative, while a false `free_public_wifi` only ever meant that nothing the city publishes is nearby. Derived from OpenStreetMap's `internet_access`, where `wlan`, `yes` and `wifi` are true and `no` is false. `wired` and `terminal` read as `null`, not as false: an ethernet port and a public computer each say there is internet without saying whether there is Wi-Fi. 295 spots are true, 42 false, 3,435 unrecorded.

`indoor_seating` is true where a contributor has recorded somewhere to sit inside, false where one has recorded that there is nowhere, and `null` otherwise. 112 true, 13 false, 3,647 unrecorded. It is rare because that is how many contributors have tagged it, and nothing infers it from anything else — not from the category, not from the presence of a sidewalk licence, not from the words in the name.

`opening_hours` is OpenStreetMap's own [opening hours syntax](https://wiki.openstreetmap.org/wiki/Key:opening_hours), served as the raw string: `Mo-Fr 07:00-19:00; Sa-Su 08:00-18:00`. 1,134 spots carry one, all of them cafés — no city source publishes a library's schedule. It is deliberately **not** turned into an "open now" flag, by this API or by the importer. Evaluating the syntax correctly needs a timezone and the public-holiday calendar the syntax can refer to, and telling someone a closed café is open is worse than telling them nothing. A client that wants "open now" has to take that on knowingly.

`indoor_seating` has a filter and an index; `venue_wifi` and `opening_hours` have neither, for the reason `outdoor_seating` has neither — they are attributes the API reports rather than ones it narrows on, and an index on a column nothing queries is a write cost for nothing. The asymmetry is deliberate. A filter over a three-state column has to decide what `false` means about the unrecorded majority, and only `indoor_seating` has an answer worth offering: "recorded as having nowhere to sit inside" is a real, if small, thing to ask for. See [Filtering](#filtering) for exactly what each value selects.

```{important}
`university` is an addition to the previously agreed contract and still needs owner sign-off. It is proximity and nothing else: it names the closest campus within 500 metres, or the campus itself for a campus record, and is `null` when no campus is that close. The campus list is curated — the college and university records of the city's facilities database — and the field is never guessed from a spot's name, its operator, or anything else. It is not an affiliation, an endorsement, or an access claim: a named campus does not mean the institution is connected to the spot or that the public may use the room. In the example above, 169 metres separate a public library branch from a campus with no relationship to it.

Cafés never carry one. A café is a third place in its own right rather than somewhere reached through a campus, and the measurement bears that out: FacDB stores a single point per institution whatever its size, so Columbia's whole campus is one coordinate with its nearest café 181 metres away, while a school occupying one floor has one at 67 metres. Any radius would drop the universities students attend before the vocational schools nobody is looking for.
```

## Listing study spots

`GET /spots` returns one page of spots inside a stable envelope:

```json
{
  "items": [],
  "pagination": {
    "limit": 20,
    "offset": 0,
    "count": 0,
    "total": 1900,
    "has_more": false
  }
}
```

`total` counts every spot matching the filters, ignoring the page window. `count` is the number of items on this page, and `has_more` is true when `offset + count < total`.

Results are ordered by name, then by identifier. Because the identifier is unique, that sort key is total, so paging over an unchanged dataset never repeats or skips a spot. What the contract promises is that the order does not move between requests, not the exact sequence: where in the alphabet punctuation and digits fall is the database collation's business.

### Query parameters

| Parameter | Type | Default | Behavior |
|---|---|---|---|
| `name` | string | — | Case-insensitive substring match. `%` and `_` are matched literally. |
| `neighborhood` | string | — | Case-insensitive exact match. |
| `borough` | string | — | Case-insensitive exact match on one of the five borough names. |
| `university` | string | — | Case-insensitive exact match. Spots with no curated campus affiliation are excluded. |
| `limit` | integer | `20` | Page size, between 1 and 100. |
| `offset` | integer | `0` | Rows to skip before the page starts. |

Filters combine with AND. Text filters are trimmed, must not be blank, and are limited to 120 characters. A `borough` value is also normalized for internal spacing, so `?borough=brooklyn` and `?borough=  Staten   Island ` both resolve.

Case-insensitivity covers the whole of Unicode, not only ASCII, so `?name=café` and `?name=CAFÉ` return the same spots. Folding is the database's, applied identically to the stored value and the filter value, and every environment runs a UTF-8 cluster; the one place it is less aggressive than the previous implementation is `ß`, which Postgres does not fold to `ss`, so "strasse" does not match "Straße". See [Why no column declares a collation](database.md#why-no-column-declares-a-collation).

Unknown query parameters are rejected rather than ignored, so a misspelled filter fails loudly instead of silently returning unfiltered results:

```shell
curl --fail 'http://localhost:7501/spots?borough=Brooklyn&name=library&limit=5'
```

## Errors

Every non-2xx response uses one envelope:

```json
{
  "error": {
    "code": "validation_error",
    "message": "The request could not be validated.",
    "details": [
      {
        "field": "query.limit",
        "message": "Ensure this value is less than or equal to 100.",
        "type": "max_value"
      }
    ]
  }
}
```

`code` is stable and machine-readable; `message` is for people. `details` lists one entry per offending input and is empty when no single input is at fault.

| Status | `code` | Raised when |
|---|---|---|
| 404 | `not_found` | No spot has the requested identifier. |
| 405 | `method_not_allowed` | The route exists but the method does not. |
| 422 | `validation_error` | A parameter is missing, malformed, out of range, or unrecognized. |
| 500 | `internal_error` | An unhandled failure. The cause is logged, never returned. |
| 503 | `database_unavailable` | Postgres could not answer the query, or has never been migrated. |

## Filtering

Both `GET /spots` and `GET /spots/search` take the same filters: `neighborhood`,
`borough`, `category`, `university`, `free_public_wifi`, `no_purchase_needed`, and
`indoor_seating`. They combine with
AND, so supplying two narrows rather than widens, and on the search endpoint
they narrow the candidates *before* ranking. Filtering after ranking would drop
the best matches out of a page rather than out of the result set, and the
reported total would describe something the caller never sees.

`free_public_wifi` and `no_purchase_needed` each take `true` or `false`. False
is a filter in its own right -- places that do expect a purchase, which is every
café -- not the absence of one.

`indoor_seating` also takes `true` or `false`, and **its `false` does not mean
what the other two mean.** The column has three states, so `?indoor_seating=false`
is "places somebody recorded as having nowhere to sit inside" -- 13 spots -- and
*not* "places not known to have indoor seating", which would be 3,647 and would
be asserting something about every one of them. Both values therefore exclude
the unrecorded majority: this filter narrows to a recorded answer rather than to
the absence of one. `?indoor_seating=true` returns around 112 spots, which is how
many contributors have tagged, and a client showing this control should show the
facet count beside it so a reader can see that before ticking.

`venue_wifi` and `opening_hours` have no filter, and that is not an oversight.
`?venue_wifi=false` would be a question whose honest answer is 42 rows and whose
tempting wrong answer is 3,435, and a schedule in OpenStreetMap's syntax is not
something to match on without evaluating it -- see
[the three fields where `null` is an answer](#the-three-fields-where-null-is-an-answer).

A present but empty parameter is a `422`, the same as an unrecognized one: a
filter whose value was lost should fail rather than quietly widen the search.

### `GET /spots/facets`

```json
{
  "boroughs": [{ "value": "Manhattan", "count": 151 }],
  "categories": [{ "value": "library", "count": 248 }],
  "universities": [{ "value": "New York University", "count": 12 }],
  "free_public_wifi": 567,
  "no_purchase_needed": 264,
  "indoor_seating": 112
}
```

What the filters can be set to, with how many spots carry each value. A client
cannot derive this from the contract: `borough` is five fixed names, but the
category vocabulary belongs to the importer and the campuses are whatever the
snapshot contains, so a hard-coded list would silently stop matching when the
data changes. Counts are included because offering a value that matches nothing
is worse than not offering it.

`free_public_wifi`, `no_purchase_needed` and `indoor_seating` are single numbers
rather than lists of values, because the controls they serve are checkboxes: the
only useful count is how many spots remain when each is ticked. `indoor_seating`
counts the spots recorded as *having* it rather than the spots not recorded as
lacking it, so it is small on purpose -- padding it with the unrecorded majority
would make the number a guess.

The endpoint takes every filter the listing endpoints take, plus `q`, all
optional, and no `limit` or `offset` -- a facet list is as long as the number of
distinct values, and paging it would mean a control that offers only some of
them. With nothing supplied it describes the whole snapshot.

**Each count reflects the request already in force, except for its own filter.**
A count is a promise about what picking that value returns, and counted over the
whole table every one of them stops being true the moment anything else is
narrowing the results: under `?borough=Bronx` the unfiltered category counts
would still offer a type the Bronx does not contain. Its own filter is left out
so that a chosen value does not hide the alternatives -- with `?borough=Bronx`
all five boroughs are still listed, so there is a way to switch, while
`categories`, `universities`, `free_public_wifi`, `no_purchase_needed` and
`indoor_seating` narrow to the Bronx.

A client that filters should refetch this whenever the filters or the query
change, which is one request per interaction. Returning results and facets in
one response would avoid that; two requests is the cost of keeping ranking and
counting in Postgres.

## Searching

`GET /spots/search?q=` ranks spots instead of filtering them, in the same
envelope `GET /spots` returns. It takes `q`, the filters above, `limit` and
`offset`, rejects any other parameter, and orders results by relevance rather
than by name.

The difference matters at the search box. `GET /spots` answers "does this
match": `?name=libary` returns nothing, and so does `?name=NYPL`. `search`
answers "which of these is closest", so both find what the person meant.

### Two passes

Finding every word someone typed and surviving a misspelling pull in opposite
directions, so they are separate passes and the order is the design.

**Full text runs first.** The query goes through `websearch_to_tsquery` and
every word has to appear somewhere in the row, matched against four fields that
count for different amounts:

| Field | Weight | Why |
|---|---|---|
| `name` | highest | what the place is called is almost always what was meant |
| `university`, `operator` | second | which institution this is — the campus it sits by, and who runs it |
| `neighborhood` | third | where it is, not what it is |
| `address`, `borough`, `category` | lowest | a place *called* Washington beats the places *on* Washington Street |

`operator` is who runs the place, and it is the only field that connects a
branch to its library system: a branch is named after its neighbourhood —
*Howard Beach*, *Fresh Meadows*, *Glendale* — so nothing else in the record says
whether it is NYPL, BPL or QPL. Without it `qpl` found two spots; with it, 68.
It is null for cafés, whose licence names only the company holding it, and for
academic and special libraries it simply repeats the facility's own name.

`borough` and `category` are matched despite each having a filter of its own,
because a search box is where people type them first. Without them
`bronx public library` found three spots and put a Manhattan one first, and
`manhattan library` found five of the sixty-eight.

They cannot flood a result set, because every word still has to match:
`bobst library` returns the one library named Bobst, since only one row matches
both words. A bare `cafe` does grow to every café, which is what the word means.
The category needs no transformation either -- Postgres splits on the
underscore, so `public_library` indexes exactly as `public library` does.

Requiring every word is what keeps `library bobst` to the one library it
describes. Scoring the query against the best-matching run of words instead --
which is what the trigram pass does -- gave it 170 results, because "library"
alone matches every library in the city.

Weighting `university` is the other half. It is proximity rather than
affiliation, but it is the only field that connects a campus to the buildings
around it: in the current snapshot 14 spots relate to NYU and just 3 say so in
their name, so searching names alone missed 11 of them.

Because this pass is `websearch_to_tsquery`, it inherits that parser's syntax
for free: `"washington square"` in quotes must match as a phrase, and a leading
`-` excludes, so `library -bobst` is every library except that one. Neither can
raise a syntax error on something typed into a box.

**Trigrams run only if that found nothing.** A misspelling produces a word
Postgres has never indexed, so full text cannot match `libary` at all. The
fallback compares the query against the best-matching run of words in the name,
and the same lower-weighted against the neighborhood, dropping anything below a
relevance of 0.45.

That figure was measured rather than chosen: a one-character typo in a
seven-letter word scores 0.5, and unrelated words sit near 0.33. At 0.6
`libary` matches nothing, which is the failure the pass exists to prevent.

Running the passes the other way round would undo the first one -- a typo-
tolerant match on "library" would bury the exact hit for `library bobst` -- so
the fuzzy pass only ever runs when the precise one has already failed. Choosing
between them costs one `EXISTS`; the alternative is blending a rank that
measures *where* a word was found with a similarity that measures *how close*
it was, into one number nobody could reason about.

### Initialisms

An initialism is expanded before the query reaches Postgres, because no fuzzy
algorithm connects `NYPL` to `New York Public Library` -- they share almost no
trigrams. Every word is expanded, so `nyu library` becomes `New York University
library` and means it. The list is in `spots/search.py`.

**The expansion is a hint, not a replacement.** If it matches nothing, the
literal term gets a turn before the fuzzy pass does. `CUNY` is the case that
proved it necessary: it expands to `City University of New York`, which no
record contains -- the campuses are named `CUNY Hunter College` -- so the single
attempt failed and the query fell through to trigrams, where `New York Cit...`
is a close match for *New York City Bagel & Coffee House*. Typing CUNY returned
bagel shops. The fuzzy pass now also runs on what was typed rather than on the
expansion, so nothing is ever matched against words the search box substituted.

### As you type

A prefix scores highly and the full-text pass is indexed, so this endpoint also
serves search-as-you-type: `bob` ranks *Elmer Holmes Bobst Library* without
anything being submitted. The browser calls it on a debounced keystroke rather
than only on submit.

The relevance score is not in the response. It exists to order results, and
publishing it would be a number the contract has to keep stable for no one's
benefit.

## Planned routes

- `GET /health/ready`

The readiness route will report required dependency failures.
