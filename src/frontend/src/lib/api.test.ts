import { describe, expect, it } from 'vitest';
import { ApiError, fetchFacets, listSpots, searchSpots } from './api';
import type { SpotPage } from './contract';

/** A page shaped like the API's, with as many identical items as asked for. */
function page(total: number, count = total, offset = 0): SpotPage {
	return {
		items: Array.from({ length: count }, (_, index) => ({
			id: `facdb:${offset + index}`,
			name: `Spot ${offset + index}`,
			category: 'library',
			address: null,
			neighborhood: 'Greenpoint',
			borough: 'Brooklyn' as const,
			latitude: 40.73,
			longitude: -73.95,
			university: null,
			operator: 'Brooklyn Public Library',
			free_public_wifi: false,
			no_purchase_needed: true,
			subway_station: 'Bedford Av',
			subway_routes: 'L',
			subway_metres: 180,
			subway_step_free: 'none',
			nearby_spots: 12,
			outdoor_seating: false,
			indoor_seating: null,
			venue_wifi: null,
			opening_hours: null
		})),
		pagination: {
			limit: 20,
			offset,
			count,
			total,
			has_more: offset + count < total
		}
	};
}

function json(body: unknown, status = 200): Response {
	return new Response(JSON.stringify(body), {
		status,
		headers: { 'content-type': 'application/json' }
	});
}

/** Records every URL it is called with, and replies from a queue. */
function recorder(...replies: Array<() => Response | Promise<Response>>) {
	const urls: string[] = [];
	let call = 0;
	const fetcher = async (input: RequestInfo | URL) => {
		urls.push(String(input));
		const reply = replies[Math.min(call++, replies.length - 1)];
		return reply();
	};
	return { urls, fetcher: fetcher as unknown as typeof globalThis.fetch };
}

describe('searchSpots', () => {
	it('calls the ranked search endpoint with the default page size', async () => {
		const { urls, fetcher } = recorder(() => json(page(3)));

		const result = await searchSpots('library', { fetcher });

		expect(result.pagination.total).toBe(3);
		expect(urls).toHaveLength(1);
		expect(urls[0]).toContain('/api/spots/search');
		expect(urls[0]).toContain('q=library');
		expect(urls[0]).toContain('limit=20');
		expect(urls[0]).toContain('offset=0');
	});

	it('is a single request', async () => {
		// It used to be two -- name, then neighborhood if that found nothing --
		// because no single filter could serve one search box. The ranked
		// endpoint replaced both, and a second request here would mean the
		// fallback had crept back in.
		const { urls, fetcher } = recorder(() => json(page(0, 0)));

		await searchSpots('nothing matches this', { fetcher });

		expect(urls).toHaveLength(1);
	});

	it('does not send the filter parameters the listing endpoint takes', async () => {
		const { urls, fetcher } = recorder(() => json(page(1)));

		await searchSpots('Greenpoint', { fetcher });

		expect(urls[0]).not.toContain('name=');
		expect(urls[0]).not.toContain('neighborhood=');
	});

	it('passes an offset through for paging', async () => {
		const { urls, fetcher } = recorder(() => json(page(40, 20, 20)));

		const result = await searchSpots('library', { offset: 20, fetcher });

		expect(result.pagination.offset).toBe(20);
		expect(urls[0]).toContain('offset=20');
	});

	it('encodes a query that contains characters a URL would eat', async () => {
		const { urls, fetcher } = recorder(() => json(page(1)));

		await searchSpots('100% Coffee & Tea', { fetcher });

		expect(urls[0]).toContain('q=100%25+Coffee+%26+Tea');
	});

	it('passes a misspelling through untouched, because the server ranks it', async () => {
		// Typo tolerance is trigram similarity in Postgres, not anything the
		// browser should try to be clever about.
		const { urls, fetcher } = recorder(() => json(page(1)));

		await searchSpots('libary', { fetcher });

		expect(urls[0]).toContain('q=libary');
	});
});

describe('error handling', () => {
	it('reports the API error code and message from the envelope', async () => {
		const { fetcher } = recorder(() =>
			json(
				{
					error: {
						code: 'validation_error',
						message: 'The request could not be validated.',
						details: []
					}
				},
				422
			)
		);

		const failure = await searchSpots('x', { fetcher }).catch((error: unknown) => error);

		expect(failure).toBeInstanceOf(ApiError);
		expect((failure as ApiError).code).toBe('validation_error');
		expect((failure as ApiError).status).toBe(422);
	});

	it('distinguishes a database outage, which the page words differently', async () => {
		const { fetcher } = recorder(() =>
			json(
				{
					error: {
						code: 'database_unavailable',
						message: 'The study-spot database is unavailable.',
						details: []
					}
				},
				503
			)
		);

		const failure = await searchSpots('x', { fetcher }).catch((error: unknown) => error);

		expect((failure as ApiError).code).toBe('database_unavailable');
	});

	it('reports a transport failure as a network error rather than a status', async () => {
		const { fetcher } = recorder(() => {
			throw new TypeError('Failed to fetch');
		});

		const failure = await searchSpots('x', { fetcher }).catch((error: unknown) => error);

		expect((failure as ApiError).code).toBe('network_error');
		expect((failure as ApiError).status).toBe(0);
	});

	it('reports a non-JSON body rather than throwing a parse error at the caller', async () => {
		const { fetcher } = recorder(
			() => new Response('<html>502 Bad Gateway</html>', { status: 502 })
		);

		const failure = await searchSpots('x', { fetcher }).catch((error: unknown) => error);

		expect((failure as ApiError).code).toBe('invalid_response');
	});

	it('still reports an error when a failure carries no envelope', async () => {
		const { fetcher } = recorder(() => json({ Message: null }, 403));

		const failure = await searchSpots('x', { fetcher }).catch((error: unknown) => error);

		expect((failure as ApiError).status).toBe(403);
	});
});

describe('listSpots', () => {
	it('asks for a page with no filter', async () => {
		const { urls, fetcher } = recorder(() => json(page(380, 20)));

		const result = await listSpots({ fetcher });

		expect(result.pagination.total).toBe(380);
		expect(urls[0]).toContain('/api/spots?');
		expect(urls[0]).not.toContain('q=');
	});
});

describe('filters', () => {
	it('sends the filters it is given', async () => {
		const { urls, fetcher } = recorder(() => json(page(2)));

		await searchSpots('library', {
			filters: { borough: 'Bronx', category: 'library', free_public_wifi: true },
			fetcher
		});

		expect(urls[0]).toContain('borough=Bronx');
		expect(urls[0]).toContain('category=library');
		expect(urls[0]).toContain('free_public_wifi=true');
	});

	it('omits a cleared filter rather than sending it blank', async () => {
		// Both endpoints answer a present-but-blank parameter with 422, so a
		// cleared dropdown has to drop the key, not send an empty value.
		const { urls, fetcher } = recorder(() => json(page(2)));

		await searchSpots('library', {
			filters: { borough: '', category: undefined, free_public_wifi: true },
			fetcher
		});

		expect(urls[0]).not.toContain('borough=');
		expect(urls[0]).not.toContain('category=');
		expect(urls[0]).toContain('free_public_wifi=true');
	});

	it('applies filters to a plain listing too, for browsing without a query', async () => {
		const { urls, fetcher } = recorder(() => json(page(5)));

		await listSpots({ filters: { borough: 'Queens' }, fetcher });

		expect(urls[0]).toContain('/api/spots?');
		expect(urls[0]).toContain('borough=Queens');
		expect(urls[0]).not.toContain('q=');
	});

	it('sends false as a value rather than dropping it', async () => {
		// "Without free Wi-Fi" is a filter, not an absence of one.
		const { urls, fetcher } = recorder(() => json(page(1)));

		await listSpots({ filters: { free_public_wifi: false }, fetcher });

		expect(urls[0]).toContain('free_public_wifi=false');
	});
});

describe('fetchFacets', () => {
	const facetBody = () =>
		json({
			boroughs: [{ value: 'Manhattan', count: 151 }],
			categories: [{ value: 'library', count: 248 }],
			universities: [{ value: 'New York University', count: 12 }],
			free_public_wifi: 206,
			no_purchase_needed: 264
		});

	it('reads the values the filter controls offer', async () => {
		const { urls, fetcher } = recorder(facetBody);

		const facets = await fetchFacets({ fetcher });

		expect(urls[0]).toContain('/api/spots/facets');
		expect(facets.boroughs[0]).toEqual({ value: 'Manhattan', count: 151 });
	});

	it('reads the Wi-Fi count as a single number', async () => {
		const { fetcher } = recorder(facetBody);

		expect((await fetchFacets({ fetcher })).free_public_wifi).toBe(206);
	});

	it('asks for nothing when no filter is in force', async () => {
		const { urls, fetcher } = recorder(facetBody);

		await fetchFacets({ fetcher });

		// Not a trailing '?': the counts describe the whole snapshot.
		expect(urls[0]).toBe('/api/spots/facets');
	});

	it('passes the active filters along', async () => {
		const { urls, fetcher } = recorder(facetBody);

		await fetchFacets({
			filters: { borough: 'Bronx', free_public_wifi: true, no_purchase_needed: true },
			fetcher
		});

		expect(urls[0]).toContain('borough=Bronx');
		expect(urls[0]).toContain('free_public_wifi=true');
		expect(urls[0]).toContain('no_purchase_needed=true');
	});

	it('reads the no-purchase count as a single number', async () => {
		const { fetcher } = recorder(facetBody);

		expect((await fetchFacets({ fetcher })).no_purchase_needed).toBe(264);
	});

	it('passes the query along, so the counts describe the search', async () => {
		const { urls, fetcher } = recorder(facetBody);

		await fetchFacets({ query: 'library', fetcher });

		expect(urls[0]).toContain('q=library');
	});

	it('drops a filter that was cleared', async () => {
		const { urls, fetcher } = recorder(facetBody);

		await fetchFacets({ filters: { borough: '' }, fetcher });

		// An empty value is a 422 at both endpoints, so it is omitted instead.
		expect(urls[0]).toBe('/api/spots/facets');
	});

	it('reports a transport failure as a network error', async () => {
		const { fetcher } = recorder(() => {
			throw new TypeError('Failed to fetch');
		});

		const failure = await fetchFacets({ fetcher }).catch((error: unknown) => error);

		expect((failure as ApiError).code).toBe('network_error');
	});
});
