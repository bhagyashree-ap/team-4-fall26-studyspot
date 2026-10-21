# Study-spot data

This directory is the small boundary between NYC Open Data and StudySpot:

```text
NYC Open Data  -\
osm_cafes.json --- ingest.py -> spots.json
```

- `ingest.py` downloads NYC Open Data and normalizes it into the shared contract.
- `spots.json` is the canonical generated dataset consumed by the application.
- `osm.py` fetches the OpenStreetMap cafés from the Overpass API, and `osm_cafes.json` is what it
  last wrote. Separate from `ingest.py` and committed, like `subway_stations.json`.
- `test_ingest.py` and `test_osm.py` test the mapping.
- `fixtures/` is a trimmed copy of what the upstream datasets return, so the tests and
  `--fixtures` need no network.

Regenerating the snapshot is how the data changes:

```shell
just ingest
just load-data
```

`spots.json` stays in version control, so a checkout can load the serving table and run the API
without reaching NYC Open Data. Nothing writes to it at runtime. Database migrations, local
database files, and search indexes do not belong here; the backend's `load_spots` management
command copies this snapshot into the Postgres serving table, replacing its contents in one
transaction.

A spot contains `id`, `name`, `category`, `address`, `neighborhood`, `borough`, `latitude`, and
`longitude`, plus `university`. A field outside that set makes the loader fail rather than
disappear silently, and the importer checks its own output against the same set first, because
its errors name the record and the loader's arrive at deployment time.

## Where the records come from

The city's [Facilities Database][facdb] (FacDB, Socrata `ji82-xba5`), which is what the `facdb:`
identifier prefix refers to. Two subsets of it are places a student might read in — the
`LIBRARIES` facility group and the `COLLEGES OR UNIVERSITIES` subgroup — which is 390 public,
academic, and institutional libraries and campuses across the five boroughs.

Cafés come from [DOHMH Restaurant Inspection Results][dohmh] (`43nn-pn8j`) filtered to
`cuisine_description = 'Coffee/Tea'`, which is what the `dohmh:` prefix refers to. That is about
2,160 establishments. `cuisine_description` is the health department's own classification of what
a place serves, chosen from a fixed list, and it is the whole of the category test: the importer
does not read names, because deciding what a business is from the words in its name is guessing.

That dataset is one row per inspection — roughly 21,000 rows for those establishments — so the
importer folds it down to the most recent inspection of each `camis`. The most recent row is the
one whose `action` says whether the place is currently closed and whose address and geocode are
the freshest the city has. `dba` and `(building, street)` are constant within every `camis` in the
dataset, so no choice of row here could change a published name or address.

Cafés also come from [OpenStreetMap][osm] by way of the [Overpass API][overpass], queried for
`amenity=cafe` inside the city's bounding box — 3,011 records, of which 2,978 have a name and
reach `osm_cafes.json`. That is what the `osm:` prefix refers to. The source is **additive**: see
"OpenStreetMap is additive, and the join is the dangerous part" below.

Sidewalk-dining licences come from [Dining Out NYC][dining] (`fpeh-f7ci`), read for the
`outdoor_seating` attribute alone. Only `Issued` `Sidewalk` licences: the register also carries
applications that were never granted, and crediting a café with seating on the strength of an
ungranted application would be a false statement about a real business, while a `Roadway` licence
is a dining structure in a parking lane rather than somewhere to sit with a laptop.

Neighborhood names come from the [2020 Neighborhood Tabulation Areas][nta] (`9nt8-h7nd`), read two
ways. FacDB publishes the 2020 code but not its name, so a facility's neighborhood is a dictionary
lookup. DOHMH publishes no 2020 code — its `nta` column is the 2010 vintage, four characters where
a 2020 code is six — so a café's neighborhood *and* borough come from locating its coordinates
inside the boundary polygons. That costs a 4.5 MB download of coastline per run and is worth it:
joining 2010 codes to 2010 names would put two neighborhood vocabularies in one snapshot and make
the `neighborhood` filter depend on which source a spot came from.

Requests identify themselves and page politely. `NYC_OPEN_DATA_APP_TOKEN` raises the rate limit
from the shared anonymous pool to a personal one; the importer runs without it, and the token is
read from the environment so it never reaches version control.

FacDB itself lists no cafés, and never will: it is a register of facilities the city *operates*,
while a café is a business the city *inspects*.

### What a cuisine classification does and does not say

It says the health department recorded this establishment as serving coffee or tea, which is the
question the category asks. It says nothing about hours, Wi-Fi, power, noise, seating, or whether
anyone may sit with a laptop and one coffee for three hours. The contract has no field for any of
that and the application promises none.

It is still an inspection log rather than a directory of open businesses. An establishment closed
at its most recent inspection is dropped, which catches inspection-ordered closures and nothing
else: **a café that shut quietly, with no final inspection to record it, is still in here**, and
nothing in the data says so. That is the price of the category meaning anything at all.

### What this replaced, and why

Until this was fixed, cafés came from Dining Out NYC and *every row of it* was published as a café
on the strength of holding an outdoor-dining licence. A sidewalk licence says a business puts
tables on the pavement; it says nothing whatever about what the business sells. Of the 1,652
records that reached the snapshot that way, around 270 read as bars, pubs, pizzerias or
restaurants — *Good Bar*, *P.Mcdaid's Irish Pub*, *Mchale's Bar & Grill*, *Koronet Pizza* —
against about 210 whose name reads like a coffee shop. The application was telling students an
Irish pub was a café. It also missed every indoor-only coffee shop in the city, because no
pavement tables meant no licence and so no row.

Regenerating against DOHMH took that measure from 272 names reading as a bar, pub, pizzeria or
restaurant down to 28, on a set of cafés 31% larger.

### What it cost, and what OpenStreetMap gets back

Precision rose and recall fell. A cuisine code is one value per establishment chosen from a fixed
list, so a café that sells sandwiches can be filed under something else — *Caffe Reggio*, open on
MacDougal Street since 1927, is recorded as `Italian`. Filtering on `Coffee/Tea` loses it, and it
went missing from the live site. That regression is why OpenStreetMap is read.

## OpenStreetMap is additive, and the join is the dangerous part

`amenity=cafe` is a human judgement about what a place *is*, which is the question the category
asks, rather than a code about what its kitchen serves. It is not a name match either, which was
the other option and was rejected: a name says nothing about whether somewhere is a study spot,
and matching café words in a business name pulls in every deli called *Cafe Metro*. OSM does not
have that problem because it tags a deli as `shop=deli` — of 3,011 `amenity=cafe` records in the
city, 15 have "deli", "bodega" or "grocery" anywhere in the name.

**This source only ever adds.** DOHMH remains the spine for which establishments exist and where:
all 2,158 of its cafés are still in the snapshot, unrenamed, unmoved and unrecategorized. The café
source has been swapped once already and it cost real records; this was written so that it could
not. `TestOpenStreetMapIsAdditive` in `test_ingest.py` holds that line field by field.

A wrong join silently attaches one venue's attributes to another, which has happened on this
project before. So a match needs the normalized name **and** the location to agree, never one
alone:

- name and street address both agree, and the two geocodes are within 200 m, or
- the name agrees and the two points are within 150 m.

150 m is measured rather than chosen. Among the 438 pairs that agree on name *and* address, the
two sources' geocodes sit a median 18 m apart, 90% within 49 m and 95% within 68 m — so an OSM
*Starbucks* 150 m from a DOHMH *Starbucks* is that Starbucks, while one 400 m away is a different
branch that must not inherit its hours. A record two establishments both answer, or an
establishment two records both claim, joins to neither: one of the two would be wrong and nothing
says which.

An unmatched record is then tested the other way round, because the risk turns over — publishing
it could duplicate a café the snapshot already has under a differently-spelled name. 496 OSM cafés
sit within 30 m of a DOHMH café whose name does not match, and reading forty of them by hand,
about half are one business written two ways — *La Colombe Coffee Roasters* and *La Colombe*,
*Coffee Project New York* and *Coffee Project NY*, *Devoción* and *Devocion* — while the other half
are two businesses next door: *Rise Brewing Company* at 79 Delancey and *Starbucks* at 80,
*Grabstein's Bagels* at 651 Broadway and *Gregory's Coffee* at 649. Proximity cannot tell those
apart, so the street address does: within 75 m of a DOHMH café, an OSM record is published only
when both carry an address and the two differ. Otherwise it is dropped.

75 m is that same 95th percentile — how far one storefront can appear to move between the two
registers. Past it, two records are two places.

Against the live data: **649 enriched, 1,352 published as new spots, 600 dropped as ambiguous**,
377 outside the city and 33 with no name. The 377 are the Overpass bounding box being a rectangle
where the city is not — it reaches into Essex County and Westchester, and the neighborhood
boundary polygons keep those out exactly as they do for DOHMH, after `NYC_BOUNDS` has had its
cheaper go first.

Dropping 600 costs recall, which is what this source was added for, so the trade is worth stating:
the alternative is a second pin for one café, twice in the result list, two detail pages, and both
of them half right.

### Three fields where `null` is an answer

`indoor_seating`, `venue_wifi` and `opening_hours` are the only fields in the contract where
`null` means *nobody has recorded this* rather than *this record has no such thing*. **Nothing may
read `null` as `false`.** Everywhere else a null is an absence of the thing and reading it as a
negative is harmless; here it is the difference between "somebody went and looked and there is no
Wi-Fi" and "nobody has said", and telling those apart is the whole point.

| field | true | false | unrecorded |
| --- | --- | --- | --- |
| `indoor_seating` | 112 | 13 | 3,647 |
| `venue_wifi` | 295 | 42 | 3,435 |
| `opening_hours` | 1,134 recorded | — | 2,638 |

`venue_wifi` comes from `internet_access`, where `wlan`, `yes` and `wifi` are true and `no` is
false. `wired` and `terminal` read as unrecorded, not as false: an ethernet port and a public
computer each say there is internet without saying whether there is Wi-Fi. A value nobody has
thought about reads as unrecorded too, because the mapping is a table rather than a truthiness
test.

**`venue_wifi` is not `free_public_wifi` and is deliberately a separate field.** One is the Wi-Fi
the venue provides; the other is a hotspot *the city publishes* within 25 m of the point, usually
a library's own and occasionally a LinkNYC kiosk on the pavement. A café can have the first and
not the second, and a library the reverse. Their falses are also worth different amounts: a false
`venue_wifi` is a trustworthy negative, while a false `free_public_wifi` only ever meant that
nothing the city publishes is nearby.

`opening_hours` is OSM's own syntax, stored as written — `Mo-Fr 07:00-19:00; Sa-Su 08:00-18:00`.
Deliberately **not** turned into an "open now": evaluating it needs a timezone and the
public-holiday calendar the syntax can refer to, and sending somebody to a closed café is worse
than telling them nothing.

OSM's own `outdoor_seating` tag is **not** read. The snapshot already has a field by that name
meaning something narrower and checkable — a Dining Out licence matching a name and an address —
and filling it from a source with a different meaning would quietly change what it claims. OSM's
version also arrives as nineteen distinct values, from `sidewalk;street` to `bench`, which is not
a boolean.

### Refreshing it

```shell
just ingest-osm
```

Rarely needed: the output is committed. One Overpass request takes about 45 seconds against a
volunteer-run service that sheds load by returning 429 and 504 under pressure, which is why it is
not part of `just ingest` and why a build does not depend on it. `osm.py` refuses a result with
fewer than 2,000 cafés rather than publishing what looks like a truncated answer — the committed
file is still good, and a snapshot quietly missing two thousand cafés is not.

### `outdoor_seating` is a join, and a strict one

A Dining Out licence sets `outdoor_seating` on a café when the licence's name *and* street address
both match. `false` means no licence matched, not that there is nowhere to sit outside.

The strictness is because the failure modes are not symmetric. Matching on street address alone
would credit a café with whichever other business shares its building: 28 cafés share an address
with a licence held under a different name, and inspecting them shows almost every one is a
different business — *787 Coffee* at 100 Lexington Ave shares its address with *Bhatti Indian
Grill*, *Joe Coffee* at 405 W 23 St with *Henry & The Lions*. A café missing its licence reads as
a `false`, which is what the field is documented to mean. A café credited with someone else's
licence is a claim about a real business that is simply untrue. Those 28 are left unmatched on
purpose, and 108 cafés carry the attribute.

The two registers spell an address differently and neither is wrong — DOHMH stores `102` and
`HICKS STREET` in separate columns where Dining Out stores `102 HICKS STREET` — so street types,
compass directions and ordinals are folded to one form before comparing. Those match keys are
never published.

## A curated building beats the open-data row describing it

FacDB registers *New York University Libraries* as an academic library at Bobst's coordinates,
12 m from the curated `nyu:bobst-library`, with the **building name where a street address
belongs** — "Elmer H Bobst Library, New York, NY 10012" — and "LIU-New York University Campus",
which is Long Island University, as its campus. A search for "bobst" returned both records,
because the search vector includes the address. The curated record wins: it has the real street
address and the right university.

Three conditions, and each one is there because dropping it costs real records.

**Same category.** Nine non-curated records sit within 60 m of a curated building in the live
data and all nine are cafés — *Peet's Coffee @ NYU* 10 m from the Kimmel Center, *Blank Street
Coffee* 26 m from Rogers Hall, *The Uncommons* 24 m from the Global Center, *Think Coffee* 37 m
from Courant. They are cafés inside or beside the building and they are separate study spots. A
rule that went on distance alone would delete all nine to fix one duplicate.

**Within 50 m.** Two records of one category across the street are two places.

**No house number in the address.** This is the condition that is easy to leave out, and leaving
it out costs a real record. *Two* academic libraries sit within 50 m of Bobst: the generic FacDB
row above, and *NYU Tamiment Library* at 17 m — the Tamiment Library and Robert F. Wagner Labor
Archives, a named special collection on Bobst's tenth floor, publishing its own street address.
Same category, well inside the radius, and not a duplicate of anything.

So the test is not "is it near the building" but **"does it claim an address of its own"**. A row
that cannot say what street it is on, sitting on a curated building of the same kind, has recorded
that building. A row with a street address is asserting a place, and is kept even when the street
is the curated record's own — Tamiment is at Bobst's address, because it is on Bobst's tenth
floor.

One record is dropped in the live data, and the importer names it on stderr rather than deleting
it quietly.

## Subway stations

`subway_stations.json` is a second committed snapshot, written by `subway.py` from the MTA's
[Subway Stations][subway] (`39hk-dx4f`) on the *state* portal. It is not a study-spot source:
nothing in it reaches the `spots` table or the API. The frontend build measures each detail page's
nearest station against it, the same way it measures distance between spots.

Rows are merged on the MTA's `complex_id`, turning 496 into 445. Without that a station appears
once per line and a page shows half its trains — W 4 St-Wash Sq is published twice, as `A C E` and
as `B D F M`, at identical coordinates.

Accessibility keeps the MTA's three states rather than rounding to yes or no: `full`, `none`, and
`partial` for a platform reachable going one way and not the other. A merged complex reports its
best, because one step-free platform is what a person needs to know and which line they want is
not ours to guess.

## `operator` is who runs it

FacDB's `opname`. For the 226 public branches it is the system — 91 New York Public Library, 68
Brooklyn, 67 Queens — and it is the only field that says so: a branch is named after its
neighbourhood, so *Howard Beach* and *Fresh Meadows* carry nothing else to connect them to Queens
Public Library. The three systems have separate membership, which makes it worth publishing and
not only searching.

It is not title-cased. Upstream already capitalises this field, unlike `facname`, so passing it
through the title-caser would leave *Nyu Tamiment Library* exactly as wrong as it arrives. For
academic and special libraries it repeats the facility's own name, where it adds nothing and does
no harm. Cafés have none: DOHMH records the establishment rather than who runs it, and the licence
register it replaced named only the company holding the licence — *CGM-LLNR LLC* where the trading
name was *JEAN'S*.

## Identifiers

A café identifier is `dohmh:` and the establishment's `camis`, as in `dohmh:50037080`. `camis` is
the health department's own permit number and is stable across inspections, a renaming and a
re-geocode, which is exactly what the churn argument below asks of an identifier. The previous
source had no such key, so the identifier was a digest of name and address: renaming a café
deleted it and created a stranger in its place.

A facility identifier is the source prefix and FacDB's own `uid`, as in
`facdb:eec118768e15a5e03d3354abda7b00da`. The digest is upstream's, derived from the source
record, and the importer treats it as the record's identity rather than computing one of its own.

That choice is about churn. `load_spots` replaces the whole table rather than upserting, so an
identifier derived from a record's *contents* — its name, address, or coordinates — would change
every time the city fixed a typo or re-geocoded a building, and every row would silently come
back as a different spot with the old one deleted. Deriving it from identity alone means
re-running the importer against unchanged upstream data writes a byte-identical snapshot, and a
renamed facility is an update to one row. The prefix keeps a second source from colliding with
FacDB if its keys ever look the same.

## Categories

`cafe`, `public_library`, `special_library`, `academic_library` and `university_building` are the published vocabulary. The model leaves `category` a free string on purpose, so the vocabulary lives in
`ingest.py`. The FacDB categories are keyed on its most specific facility type; `cafe` is keyed on DOHMH's
`cuisine_description` being `Coffee/Tea`. A type nobody has mapped fails the import rather than
landing in a near-enough bucket: inventing a category would publish a guess as data, and mapping
it to the closest existing one would bury the fact that FacDB changed.

`public_library` and `special_library` are separate because the difference is the one a reader
cares about. A branch of NYPL, BPL or QPL is somewhere anyone can walk into. A special library is
an institutional collection — a club's, a society's, a hospital's — and many are open by
appointment or to members only, so publishing them as public would claim access the data does not
support. That is the same overclaim `free_public_wifi` and `university` are each worded to avoid.

The institution records in FacDB's higher-education subgroup are read but never published. An
administrative point for "Daemen University-Brooklyn Branch" is a registration rather than a room,
and campus access is restricted in any case; they exist here only to anchor the `university`
label. The campus study space the snapshot does publish is the curated NYU list.

None of this is a guarantee of entry. The contract has no field for access and the application
promises none: these are candidate locations, not guarantees of Wi-Fi, outlets, seating,
quietness, or entry.

## Absent values

`address`, `neighborhood`, and `university` are genuinely absent for some records: FacDB has no
street address for three dozen library branches, and an older extract predates the 2020 NTA
column. They are written as `null`, never as an empty string — the contract distinguishes the two
and the API returns `null`.

## `university` is proximity

It names the closest campus within 500 metres, or the campus itself for a campus record, and is
`null` when no campus is that close. The campus list is curated — it is the higher-education
subset of FacDB named above, the same records the importer publishes as `university` spots — and
the field is never guessed from a facility's name, its operator, or anything else.

**Cafés never carry one.** A café is a third place in its own right, not somewhere you reach
through a campus: a library beside a campus is plausibly *its* library, while the café on the
same corner is just a café. Leaving the field set would also have been unreliable in a way no
parameter fixes. FacDB stores one point per institution whatever its size, so Columbia's entire
Morningside campus is a single coordinate and its nearest café is 181 metres away, while a school
occupying one floor has one at 67 metres. Narrowing the radius therefore drops the universities
students attend before it drops the vocational schools nobody is looking for, and `factype`,
`capacity` and `optype` cannot tell the two apart either — Columbia and the NY School of Interior
Design are both `4-YEAR INDEPENDENT`, and every campus record has a capacity of `0`.

A named campus is not an affiliation, an endorsement, or a claim that anyone may walk in. One
hundred and sixty-nine metres is what the data says about "125th Street Library" and "Touro
University - Harlem", and it says nothing more than that.

[dining]: https://data.cityofnewyork.us/resource/fpeh-f7ci
[osm]: https://www.openstreetmap.org/
[overpass]: https://overpass-api.de/
[dohmh]: https://data.cityofnewyork.us/resource/43nn-pn8j
[subway]: https://data.ny.gov/resource/39hk-dx4f
[facdb]: https://data.cityofnewyork.us/City-Government/Facilities-Database/ji82-xba5
[nta]: https://data.cityofnewyork.us/City-Government/2020-Neighborhood-Tabulation-Areas-NTAs-/9nt8-h7nd
