# Data and search

StudySpot has one small data boundary:

```text
NYC Open Data  -\
OpenStreetMap  --- data/ingest.py -> data/spots.json -> Postgres -> API
                                                     \-> search index
```

The snapshot holds 3,772 third places across the five boroughs: 3,509 cafés, 227 public library branches, 21 special libraries, 7 academic libraries and 8 NYU campus buildings. The city's 126 campus records are read but not published: an institution's administrative point is not a room, and access to a campus is restricted. They anchor the "near which campus" label instead. These are candidate locations, not guarantees of Wi-Fi, outlets, seating, quietness, or availability.

The directory intentionally stays small:

- `README.md` documents the boundary, including where the records come from and what each field means.
- `ingest.py` downloads, normalizes, and validates.
- `spots.json` is the canonical generated dataset.
- `osm.py` fetches the OpenStreetMap cafés from the Overpass API, and `osm_cafes.json` is what it last wrote.
- `test_ingest.py` and `test_osm.py` test the mapping.
- `fixtures/` is a trimmed copy of what the upstream datasets return, so the tests and `ingest.py --fixtures` need no network.

Records come from the city's [Facilities Database](https://data.cityofnewyork.us/City-Government/Facilities-Database/ji82-xba5) (FacDB, Socrata `ji82-xba5`), which is what the `facdb:` identifier prefix refers to, with neighborhood names from the [2020 Neighborhood Tabulation Areas](https://data.cityofnewyork.us/City-Government/2020-Neighborhood-Tabulation-Areas-NTAs-/9nt8-h7nd) (`9nt8-h7nd`). Cafés come from [DOHMH Restaurant Inspection Results](https://data.cityofnewyork.us/resource/43nn-pn8j) (`43nn-pn8j`) filtered to `cuisine_description = 'Coffee/Tea'`, which the `dohmh:` prefix refers to. FacDB holds no cafés and never will, because it registers what the city *operates* while a café is something the city *inspects* — and the inspector records what each establishment serves, which is the question the category asks.

That dataset is one row per inspection, so the importer folds its 21,000-odd rows down to the most recent inspection of each `camis` and publishes one record per establishment. An establishment closed at that most recent inspection is dropped; **a place that shut quietly, with no final inspection to record it, is still in here**, and nothing in the data says so. It is still an inspection log rather than a directory of open businesses, and that limit is the price of the category meaning anything at all.

Until this was fixed, cafés came from [Dining Out NYC](https://data.cityofnewyork.us/resource/fpeh-f7ci) (`fpeh-f7ci`), the register of outdoor-dining licences, and every row of it was published as a café on the strength of holding one. A sidewalk licence says a business puts tables on the pavement and nothing whatever about what it sells: of the 1,652 records that reached the snapshot that way, around 270 read as bars, pubs, pizzerias or restaurants — "Good Bar", "P.Mcdaid's Irish Pub", "Koronet Pizza" — against about 210 whose name reads like a coffee shop. It also missed every indoor-only café, because no pavement tables meant no licence and so no row. Dining Out NYC is still read, for the `outdoor_seating` attribute alone.

## OpenStreetMap, added rather than swapped for

Moving cafés onto DOHMH raised precision and cost recall. `cuisine_description` is a food-safety code chosen from a fixed list, one value per establishment, so a café that sells sandwiches can be filed under something else entirely — and [Caffe Reggio](https://www.openstreetmap.org/node/3506087030), open on MacDougal Street since 1927, is recorded as `Italian`. Filtering on `Coffee/Tea` loses it, and it went missing from the live site.

So [OpenStreetMap](https://www.openstreetmap.org/) is read too, through the [Overpass API](https://overpass-api.de/), for `amenity=cafe` inside the city's bounding box. `amenity=cafe` is a human judgement about what a place *is*, which is the question the category asks, rather than a code about what its kitchen serves. It is not a name match either, which was the other option and was rejected: a name says nothing about whether somewhere is a study spot, and matching café words in a business name pulls in every deli called "Cafe Metro". OpenStreetMap does not have that problem because it tags a deli as `shop=deli` — of 3,011 `amenity=cafe` records in the city, 15 have "deli", "bodega" or "grocery" anywhere in the name.

**This source only ever adds.** DOHMH remains the spine for which establishments exist and where they are: all 2,158 of its cafés are still in the snapshot, unrenamed, unmoved and unrecategorized. OpenStreetMap contributes attributes to the ones it can identify, and records of its own for the cafés DOHMH files under another cuisine. The café source has been swapped once already and it cost real records; this change was written so that it could not.

The join is the dangerous part, because a wrong match silently attaches one venue's attributes to another. So a match needs the normalized name **and** the location to agree, never one alone: name and street address both agreeing within 200 m, or the name agreeing within 150 m. 150 m is measured rather than chosen — among the pairs that agree on name and address, the two sources' geocodes sit a median 18 m apart and 95% within 68 m, and an OSM "Starbucks" 400 m from a DOHMH "Starbucks" is a different branch that must not inherit its hours.

An unmatched record is then tested the other way round, because publishing it could duplicate a café the snapshot already has under a differently-spelled name. 496 OSM cafés sit within 30 m of a DOHMH café whose name does not match, and reading forty of them by hand, about half are one business written two ways — "La Colombe Coffee Roasters" and "La Colombe", "Coffee Project New York" and "Coffee Project NY" — while the other half are two businesses next door: "Rise Brewing Company" at 79 Delancey and "Starbucks" at 80. Proximity cannot tell those apart, so the street address does: within 75 m of a DOHMH café, an OSM record is published only when both carry an address and the two differ. Otherwise it is dropped as ambiguous.

Against the live data that gives **649 enriched, 1,352 published as new spots, 600 dropped as ambiguous** and 377 outside the city — the Overpass bounding box is a rectangle and the city is not, so it reaches into Essex County and Westchester, and the neighborhood boundary polygons are what keeps those out, exactly as they do for DOHMH.

Dropping 600 records costs recall, which is what this source was added for, so it is worth being plain about the trade: the alternative is a second pin for one café, twice in the result list, two detail pages, and both of them half right. Three new fields come with it — `indoor_seating`, `venue_wifi` and `opening_hours` — each of which is true, false, or *unrecorded*, and the three are the only fields in the contract where a null is an answer rather than an absence. `venue_wifi` is deliberately separate from `free_public_wifi`: one is the venue's own Wi-Fi and the other a city hotspot within 25 m, and OSM's `internet_access=no` is a trustworthy negative in a way a false `free_public_wifi` has never been. See [the API contract](api.md) for what each one may and may not be read as.

`osm.py` is separate from `ingest.py` and its output is committed, the way the subway station list is: one Overpass request takes about 45 seconds against a volunteer-run service that sheds load under pressure, so it is refreshed with `just ingest-osm` rather than on every `just ingest`, and a checkout can rebuild the snapshot without reaching it.

Neither register publishes a 2020 NTA code for a café — DOHMH's `nta` column is the 2010 vintage, four characters where a 2020 code is six — so a café's neighborhood and borough come from locating its coordinates inside the NTA boundary polygons, while a facility's neighborhood is still a lookup on the code FacDB publishes. One field derived two ways is not ideal; joining 2010 codes to 2010 names would have put two neighborhood vocabularies in one snapshot and made the `neighborhood` filter depend on which source a spot came from. Regenerate the snapshot with `just ingest` and load it with `just load-data`.

Every spot contains `id`, `name`, `category`, `address`, `neighborhood`, `borough`, `latitude`, and `longitude`, plus `university`, which names the closest campus from the curated campus list within 500 metres and is null for every spot with no campus that close. Source-specific fields must be normalized before reaching the API, and the loader rejects a snapshot carrying any field outside that contract rather than dropping it silently. The importer applies the same check to its own output first, because its errors name the offending record while the loader's arrive at deployment time.

Where a curated building and an open-data record describe the same place, the curated record wins
and the other is dropped. FacDB registers "New York University Libraries" at Bobst's coordinates,
12 m from `nyu:bobst-library`, with the building name where a street address belongs and Long
Island University as its campus, so "bobst" matched two records. The rule needs three conditions
together — same category, within 50 m, and no house number in the address — because nine cafés sit
within 60 m of a curated building and "NYU Tamiment Library" is a distinct collection 17 m from
Bobst with its own street address. See [`data/README.md`](https://github.com/gcivil-nyu-org/team-4-fall26/blob/develop/data/README.md)
for the measurements.

Database code belongs to the backend's `spots` app rather than to this source-data directory: the model, the migrations, and the `load_spots` command live there, and nothing in `data/` talks to a database. The serving table and any separate search index remain rebuildable projections of `spots.json` until the product accepts non-reproducible writes — see [Postgres database](database.md).
