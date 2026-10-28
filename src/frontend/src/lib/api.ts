/**
 * The browser's view of the StudySpot API.
 *
 * Every request is relative to `/api`, which works unchanged in all three
 * places this runs: Vite proxies it to the backend in development, and
 * CloudFront routes it to the application in the deployment. Nothing here needs
 * to know a hostname.
 */

import type { ErrorDetail, ErrorEnvelope, Facets, SpotFilters, SpotPage } from './contract';

/** Matches the API's own default page size, so the first page agrees. */
export const DEFAULT_LIMIT = 20;

/**
 * An error the API reported in its own envelope, or a transport failure.
 *
 * `code` carries the API's machine-readable code where there was one, so a
 * caller can distinguish a validation problem from the database being down
 * without parsing a message meant for a person. `details` carries the
 * per-field problems a validation error names, so a form can show each one
 * beside the control it is about.
 */
export class ApiError extends Error {
	constructor(
		readonly code: string,
		message: string,
		readonly status: number,
		readonly details: ErrorDetail[] = []
	) {
		super(message);
		this.name = 'ApiError';
	}
}

/** Narrow an unknown body to the shared error envelope. */
export function isErrorEnvelope(body: unknown): body is ErrorEnvelope {
	if (typeof body !== 'object' || body === null || !('error' in body)) return false;
	const error = (body as { error: unknown }).error;
	return typeof error === 'object' && error !== null && 'code' in error && 'message' in error;
}

/** The dependency tests replace, rather than reaching for a global stub. */
export type Fetcher = typeof globalThis.fetch;

async function get(path: string, parameters: URLSearchParams, fetcher: Fetcher): Promise<SpotPage> {
	let response: Response;
	try {
		response = await fetcher(`${path}?${parameters}`, {
			headers: { accept: 'application/json' }
		});
	} catch {
		// A network failure has no status and no envelope, so it gets a code of
		// its own rather than being reported as whatever the last status was.
		throw new ApiError('network_error', 'Could not reach the StudySpot API.', 0);
	}

	let body: unknown;
	try {
		body = await response.json();
	} catch {
		throw new ApiError(
			'invalid_response',
			'The API returned a response that was not JSON.',
			response.status
		);
	}

	if (!response.ok) {
		if (isErrorEnvelope(body)) {
			throw new ApiError(body.error.code, body.error.message, response.status);
		}
		throw new ApiError('error', `The API returned ${response.status}.`, response.status);
	}

	return body as SpotPage;
}

export type SearchOptions = {
	limit?: number;
	offset?: number;
	filters?: SpotFilters;
	fetcher?: Fetcher;
};

/**
 * Render the filters as query parameters, omitting the ones not set.
 *
 * An empty string is dropped rather than sent: both endpoints reject a present
 * but blank parameter with a 422, and a cleared dropdown should mean "no
 * filter" rather than an error.
 */
function withFilters(parameters: URLSearchParams, filters: SpotFilters = {}): URLSearchParams {
	for (const [name, value] of Object.entries(filters)) {
		if (value === undefined || value === null || value === '') continue;
		parameters.set(name, String(value));
	}
	return parameters;
}

/**
 * Search spots by a single free-text query.
 *
 * `GET /spots/search` ranks rather than filters, which is what a search box
 * needs: "libary" and "kimel" are what people type, and `GET /spots` answers
 * those with nothing at all. Postgres scores every candidate with trigram
 * similarity, the best come first, and anything too weak is dropped so an
 * unrelated query still returns nothing.
 *
 * This used to be two requests -- name, then neighborhood if that found
 * nothing -- because no single filter could serve one box. The endpoint
 * replaces both.
 */
export function searchSpots(query: string, options: SearchOptions = {}): Promise<SpotPage> {
	const { limit = DEFAULT_LIMIT, offset = 0, fetcher = globalThis.fetch } = options;

	return get(
		'/api/spots/search',
		withFilters(
			new URLSearchParams({ q: query, limit: String(limit), offset: String(offset) }),
			options.filters
		),
		fetcher
	);
}

/** Fetch one page without a filter, for a default listing. */
export function listSpots(options: SearchOptions = {}): Promise<SpotPage> {
	const { limit = DEFAULT_LIMIT, offset = 0, fetcher = globalThis.fetch } = options;

	return get(
		'/api/spots',
		withFilters(
			new URLSearchParams({ limit: String(limit), offset: String(offset) }),
			options.filters
		),
		fetcher
	);
}

export type FacetOptions = {
	filters?: SpotFilters;
	/** The free text the search endpoint ranks by, when a search is in force. */
	query?: string;
	fetcher?: Fetcher;
};

/**
 * The values the filter controls offer, for the request currently in force.
 *
 * Not hard-coded in the browser: `borough` is five fixed names, but the
 * category vocabulary belongs to the importer and the campuses are whatever
 * the snapshot contains, so a hard-coded list would silently stop matching
 * when the data changes.
 *
 * The filters and query are passed along because a count is a promise about
 * what picking that value returns. Counted over the whole snapshot, every one
 * of them stops being true as soon as anything else is narrowing the results.
 */
export async function fetchFacets(options: FacetOptions = {}): Promise<Facets> {
	const { fetcher = globalThis.fetch } = options;

	const parameters = withFilters(new URLSearchParams(), options.filters);
	if (options.query) parameters.set('q', options.query);
	// Left bare when nothing is in force, rather than ending in a lone `?`.
	const search = parameters.toString();
	const path = search ? `/api/spots/facets?${search}` : '/api/spots/facets';

	let response: Response;
	try {
		response = await fetcher(path, { headers: { accept: 'application/json' } });
	} catch {
		throw new ApiError('network_error', 'Could not reach the StudySpot API.', 0);
	}

	if (!response.ok) {
		throw new ApiError('error', `The API returned ${response.status}.`, response.status);
	}

	return (await response.json()) as Facets;
}
