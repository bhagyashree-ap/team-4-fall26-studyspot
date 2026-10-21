/**
 * The shared study-spot contract, as the browser sees it.
 *
 * These mirror `spots.models.StudySpot` and the response shapes in
 * `docs/source/api.md`. They are written out rather than generated because the
 * contract is small and changes need sign-off from every consumer; a generated
 * type would let a backend change land here silently.
 *
 * Nullability follows what NYC Open Data supplies: `address` and `neighborhood`
 * are genuinely absent for some records, and `university` is absent for every
 * record the importer does not take from a curated campus list.
 */

export const BOROUGHS = ['Manhattan', 'Brooklyn', 'Queens', 'Bronx', 'Staten Island'] as const;

export type Borough = (typeof BOROUGHS)[number];

export type StudySpot = {
	/** Stable identifier, prefixed with its source dataset, as in `facdb:a1b2c3`. */
	id: string;
	name: string;
	category: string;
	address: string | null;
	neighborhood: string | null;
	borough: Borough;
	latitude: number;
	longitude: number;
	/**
	 * The closest campus within 500 m, or the campus itself for a campus record.
	 * This is proximity and never affiliation, endorsement, or a claim of access.
	 *
	 * Always null for a cafe. A cafe is a third place in its own right, not
	 * somewhere reached through a campus.
	 */
	university: string | null;
	/**
	 * Who runs the place, where the city records it.
	 *
	 * For a public library branch this is its system — New York, Brooklyn or
	 * Queens Public Library — which nothing else in the record says, because
	 * branches are named after their neighbourhood. The three systems have
	 * separate membership, so it is worth showing.
	 *
	 * Null for cafés, whose licence names only the company holding it.
	 */
	operator: string | null;
	/**
	 * Whether a free public Wi-Fi hotspot the city publishes sits within 25 m.
	 *
	 * False means none is recorded, not that there is no Wi-Fi: a campus
	 * building's Wi-Fi needs the university's credentials, and the city has no
	 * reason to know about it.
	 */
	free_public_wifi: boolean;
	/**
	 * Whether sitting down here costs nothing.
	 *
	 * True of every library and of the campus buildings, false only of cafés,
	 * so it is not any one category. Derived by the API from `category` rather
	 * than computed here, so the rule has one definition rather than two.
	 *
	 * About money and not entry: a campus building is free and still wants the
	 * university's credentials.
	 */
	no_purchase_needed: boolean;
	/**
	 * The nearest subway station within 1.2 km, derived by the importer.
	 *
	 * All four are null together — 285 of 3,772 spots have none that close,
	 * mostly on Staten Island, where the railway is not the subway. `routes` is
	 * space separated the way the MTA publishes it; `metres` is straight-line
	 * rather than walking distance; `step_free` is `full`, `partial` (one
	 * direction only) or `none`.
	 */
	subway_station: string | null;
	subway_routes: string | null;
	subway_metres: number | null;
	subway_step_free: string | null;
	/**
	 * How many other study spots are within 400 m, about a five-minute walk.
	 *
	 * A count of places, not of people: a café on a dense stretch may be empty
	 * and an isolated library may be packed. It says how lively the surrounding
	 * block is, and whether there is anywhere else to go if this one is full.
	 */
	nearby_spots: number;
	/**
	 * Whether a current Dining Out NYC sidewalk licence matches this
	 * establishment's name and address.
	 *
	 * False means no licence matched, not that there is nowhere to sit outside:
	 * the join requires both the name and the address to agree, because matching
	 * on address alone credits a cafe with the licence of whichever other
	 * business shares its building.
	 *
	 * Only cafés can carry it — nothing licenses a library to put tables on the
	 * pavement.
	 */
	outdoor_seating: boolean;
	/**
	 * Whether OpenStreetMap records somewhere to sit inside.
	 *
	 * **Three states, and `null` is not `false`.** This is the one place in the
	 * contract where a null means *nobody has recorded this* rather than *this
	 * record has no such thing*, and it is shared by `venue_wifi` and
	 * `opening_hours`. A `false` is a contributor who went and looked; a `null`
	 * is nobody having said. Rendering them the same way would turn an absence
	 * of evidence into a claim, which is the whole reason these fields exist.
	 *
	 * Rare on purpose: around 112 spots carry a true, because that is how many
	 * contributors have tagged. Nothing infers it from anything else.
	 */
	indoor_seating: boolean | null;
	/**
	 * Whether OpenStreetMap records Wi-Fi this venue provides.
	 *
	 * **Not the same claim as `free_public_wifi`, and must not be shown as
	 * though it were.** This is the venue's own Wi-Fi, as recorded by somebody
	 * who was there. `free_public_wifi` is a hotspot *the city publishes* within
	 * 25 m of the point — usually a library's own, occasionally a LinkNYC kiosk
	 * on the street. A café can easily have this and not that, and a library
	 * the reverse.
	 *
	 * The difference shows in what a `false` is worth. A `false` here is a
	 * trustworthy negative: there is no Wi-Fi for customers. A false
	 * `free_public_wifi` only ever meant that no published hotspot is nearby.
	 * `null` here means unrecorded and is the common case.
	 */
	venue_wifi: boolean | null;
	/**
	 * When the place is open, in OpenStreetMap's own syntax, as in
	 * `Mo-Fr 07:00-19:00; Sa-Su 08:00-18:00`.
	 *
	 * Served as written rather than parsed, and shown as written. Working out
	 * whether somewhere is open *now* needs a timezone and the public-holiday
	 * calendar the syntax can refer to; telling someone a closed café is open is
	 * worse than telling them nothing.
	 *
	 * `null` for every spot nobody has recorded hours for, which is every
	 * library: no city source publishes a schedule.
	 */
	opening_hours: string | null;
};

/** One value a filter can take, with how many spots carry it. */
export type Facet = {
	value: string;
	count: number;
};

/**
 * What `GET /spots/facets` reports.
 *
 * Every count reflects the filters and query already in force, minus the one
 * being counted: the boroughs list keeps all five while a borough is selected,
 * so there is still a way to switch, but its counts narrow under a category.
 *
 * `free_public_wifi` is a single number rather than a list because the control
 * is a checkbox: how many spots remain if it is ticked.
 */
export type Facets = {
	boroughs: Facet[];
	categories: Facet[];
	universities: Facet[];
	free_public_wifi: number;
	no_purchase_needed: number;
	/**
	 * How many spots are *recorded* as having somewhere to sit inside.
	 *
	 * Counted as `=== true`, never as "not false", so this is the number of
	 * places somebody has actually written it down for — around 112 citywide.
	 * It is meant to be small: it tells the reader whether the checkbox is
	 * worth ticking before they tick it, and padding it with the unrecorded
	 * majority would make it a guess.
	 */
	indoor_seating: number;
};

/**
 * The filters both endpoints accept. Every one is optional, and an omitted
 * filter means "do not narrow on this" rather than "match nothing".
 */
export type SpotFilters = {
	borough?: string;
	category?: string;
	university?: string;
	free_public_wifi?: boolean;
	no_purchase_needed?: boolean;
	/**
	 * Restrict to spots with a *recorded* answer about indoor seating.
	 *
	 * `false` here does not mean what it means on the two filters above.
	 * `free_public_wifi: false` is "places with no city hotspot nearby", which
	 * is most of the snapshot. `indoor_seating: false` is "places somebody has
	 * recorded as having nowhere to sit inside", which is 13 spots — not
	 * "places not known to have indoor seating", which would be thousands and
	 * would claim something about every one of them.
	 *
	 * So either value excludes the unrecorded majority. That is the only
	 * reading that does not assert what nobody has written down.
	 */
	indoor_seating?: boolean;
};

/** Where a page sits in the full result set. */
export type Pagination = {
	limit: number;
	offset: number;
	count: number;
	total: number;
	has_more: boolean;
};

export type SpotPage = {
	items: StudySpot[];
	pagination: Pagination;
};

/** One specific problem with a request. */
export type ErrorDetail = {
	field: string | null;
	message: string;
	type: string | null;
};

/** The envelope every non-2xx response uses. */
export type ErrorEnvelope = {
	error: {
		code: string;
		message: string;
		details: ErrorDetail[];
	};
};
