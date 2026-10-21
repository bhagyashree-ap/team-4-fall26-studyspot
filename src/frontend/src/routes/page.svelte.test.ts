/**
 * What the search box shows is what the page applies.
 *
 * These exist because of a bug where it was not true: the box owned its own
 * copy of the text and only told the page on submit, so emptying it by hand and
 * then touching a filter went on searching for the word that had been deleted.
 * The assertions are on the requests the page issues, because that is where the
 * stale query showed up -- the box looked empty the whole time.
 */

import { page, userEvent } from 'vitest/browser';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { render } from 'vitest-browser-svelte';

import Home from './+page.svelte';
import type { Facets, SpotPage, StudySpot } from '$lib/contract';

const FACETS: Facets = {
	boroughs: [
		{ value: 'Bronx', count: 48 },
		{ value: 'Manhattan', count: 120 }
	],
	categories: [{ value: 'academic_library', count: 8 }],
	universities: [{ value: 'New York University', count: 10 }],
	free_public_wifi: 34,
	no_purchase_needed: 56,
	// Deliberately much smaller than the other two: it counts the spots
	// somebody has *recorded* indoor seating for, not the ones not known to
	// lack it.
	indoor_seating: 3
};

function spot(id: string, name: string): StudySpot {
	return {
		id,
		name,
		category: 'library',
		address: null,
		neighborhood: null,
		borough: 'Bronx',
		latitude: 40.86,
		longitude: -73.86,
		university: null,
		operator: 'New York Public Library',
		free_public_wifi: false,
		no_purchase_needed: true,
		subway_station: 'W 4 St-Wash Sq',
		subway_routes: 'A C E',
		subway_metres: 409,
		subway_step_free: 'full',
		nearby_spots: 41,
		outdoor_seating: false,
		indoor_seating: null,
		venue_wifi: null,
		opening_hours: null
	};
}

/** A one-item page, claiming a second so "Show more" appears. */
function onePage(item: StudySpot, hasMore: boolean): SpotPage {
	return {
		items: [item],
		pagination: { limit: 20, offset: 0, count: 1, total: hasMore ? 2 : 1, has_more: hasMore }
	};
}

function json(body: unknown): Response {
	return new Response(JSON.stringify(body), {
		status: 200,
		headers: { 'content-type': 'application/json' }
	});
}

/** Every request the page made, in order, as path and parameters. */
let calls: { path: string; parameters: URLSearchParams }[] = [];
let realFetch: typeof globalThis.fetch;

/** The last request, excluding the facets fetch every mount makes. */
function lastRequest(): { path: string; parameters: URLSearchParams } {
	const data = calls.filter((call) => call.path !== '/api/spots/facets');
	return data[data.length - 1];
}

beforeEach(() => {
	calls = [];
	realFetch = globalThis.fetch;

	globalThis.fetch = (async (input: RequestInfo | URL) => {
		const url = new URL(String(input), window.location.origin);
		calls.push({ path: url.pathname, parameters: url.searchParams });

		if (url.pathname === '/api/spots/facets') return json(FACETS);

		if (url.pathname === '/api/spots/search') {
			// A distinct second page: the keyed `each` would throw on a repeat.
			return url.searchParams.get('offset') === '0'
				? json(onePage(spot('facdb:bobst', 'Bobst Library'), true))
				: json(onePage(spot('facdb:butler', 'Butler Library'), false));
		}

		return json(onePage(spot('facdb:allerton', 'Allerton Library'), false));
	}) as typeof globalThis.fetch;
});

afterEach(() => {
	globalThis.fetch = realFetch;
});

const box = () => page.getByLabelText('Where');
const searchButton = () => page.getByRole('button', { name: 'Search' });

describe('the search box', () => {
	it('searches for what it holds when submitted', async () => {
		render(Home);

		await box().fill('library');
		await searchButton().click();

		await expect.element(page.getByText('Bobst Library')).toBeInTheDocument();
		expect(lastRequest().path).toBe('/api/spots/search');
		expect(lastRequest().parameters.get('q')).toBe('library');
	});

	it('stops a filter searching for a word deleted from it', async () => {
		render(Home);

		await box().fill('library');
		await searchButton().click();
		await expect.element(page.getByText('Bobst Library')).toBeInTheDocument();

		// Emptied by hand, with no second submit -- exactly the reported bug.
		await box().clear();
		await page.getByLabelText(/^Borough/).selectOptions('Bronx');

		await expect.element(page.getByText('Allerton Library')).toBeInTheDocument();
		expect(lastRequest().path).toBe('/api/spots');
		expect(lastRequest().parameters.get('q')).toBeNull();
		expect(lastRequest().parameters.get('borough')).toBe('Bronx');
	});

	it('keeps applying a word that is still showing when a filter changes', async () => {
		render(Home);

		await box().fill('library');
		await page.getByLabelText(/^Borough/).selectOptions('Bronx');

		await expect.element(page.getByText('Bobst Library')).toBeInTheDocument();
		expect(lastRequest().path).toBe('/api/spots/search');
		expect(lastRequest().parameters.get('q')).toBe('library');
		expect(lastRequest().parameters.get('borough')).toBe('Bronx');
	});

	it('clears the results when an emptied box is submitted', async () => {
		render(Home);

		await box().fill('library');
		await searchButton().click();
		await expect.element(page.getByText('Bobst Library')).toBeInTheDocument();

		// Previously a no-op, which left no way to undo a search at all.
		await box().clear();
		await searchButton().click();

		await expect
			.element(page.getByRole('region', { name: 'Search results' }))
			.not.toBeInTheDocument();
	});
});

describe('paging', () => {
	it('continues the request the visible results came from', async () => {
		render(Home);

		await box().fill('library');
		await searchButton().click();
		await expect.element(page.getByText('Bobst Library')).toBeInTheDocument();

		await page.getByRole('button', { name: 'Show more' }).click();

		await expect.element(page.getByText('Butler Library')).toBeInTheDocument();
		expect(lastRequest().parameters.get('q')).toBe('library');
		expect(lastRequest().parameters.get('offset')).toBe('1');
	});
});

describe('the place card', () => {
	it('copies a link to the spot when sharing', async () => {
		// The link is the prerendered detail page, so whoever receives it opens
		// real HTML rather than a shell that has to fetch first.
		const written: string[] = [];
		const realClipboard = navigator.clipboard;
		Object.defineProperty(navigator, 'clipboard', {
			configurable: true,
			value: {
				writeText: async (text: string) => {
					written.push(text);
				}
			}
		});

		try {
			render(Home);
			await box().fill('library');
			await searchButton().click();
			await expect.element(page.getByText('Bobst Library')).toBeInTheDocument();

			await page.getByRole('button', { name: 'Share' }).first().click();

			await expect.element(page.getByText('Copied')).toBeInTheDocument();
			expect(written[0]).toContain('/spots/facdb:bobst');
		} finally {
			Object.defineProperty(navigator, 'clipboard', {
				configurable: true,
				value: realClipboard
			});
		}
	});

	it('offers a link straight into a maps app', async () => {
		// A hyperlink rather than an embedded map: nothing is loaded from
		// anyone else to render a card.
		render(Home);

		await box().fill('library');
		await searchButton().click();
		await expect.element(page.getByText('Bobst Library')).toBeInTheDocument();

		const maps = page.getByRole('link', { name: 'Maps' }).first();
		await expect.element(maps).toBeInTheDocument();
		expect(await maps.element().getAttribute('href')).toContain('google.com/maps');
	});

	it('names who runs the place', async () => {
		// A branch is named after its neighbourhood, so its own name never says
		// which library system it belongs to -- and the three have separate
		// membership.
		render(Home);

		await box().fill('library');
		await searchButton().click();

		await expect.element(page.getByText('New York Public Library')).toBeInTheDocument();
	});
});

/** Every facets request, in order. */
function facetRequests() {
	return calls.filter((call) => call.path === '/api/spots/facets');
}

describe('the filter counts', () => {
	it('are fetched for the whole snapshot on arrival', async () => {
		render(Home);

		await expect.element(page.getByLabelText(/^Borough/)).toBeInTheDocument();
		expect(facetRequests()[0].parameters.toString()).toBe('');
	});

	it('are refetched for the narrowed results when a filter changes', async () => {
		// The reason this endpoint takes parameters at all: counted over the
		// whole table, "Academic library (8)" goes on being shown next to a
		// borough that holds one of them.
		render(Home);

		await page.getByLabelText(/^Borough/).selectOptions('Bronx');
		await expect.element(page.getByText('Allerton Library')).toBeInTheDocument();

		const latest = facetRequests()[facetRequests().length - 1];
		expect(latest.parameters.get('borough')).toBe('Bronx');
	});

	it('are refetched for the search as well', async () => {
		render(Home);

		await box().fill('library');
		await searchButton().click();
		await expect.element(page.getByText('Bobst Library')).toBeInTheDocument();

		const latest = facetRequests()[facetRequests().length - 1];
		expect(latest.parameters.get('q')).toBe('library');
	});

	it('put the no-purchase count on its checkbox', async () => {
		// Not any one category: true of every library and of the campus
		// buildings, false only of cafes, so it cannot be read off the Type
		// control.
		render(Home);

		await expect.element(page.getByText('(56)')).toBeInTheDocument();
	});

	it('put the Wi-Fi count on its checkbox', async () => {
		// A checkbox has no list of values, so the count is how many of the
		// matching spots have Wi-Fi -- the answer to "is this worth ticking".
		render(Home);

		await expect.element(page.getByText('(34)')).toBeInTheDocument();
	});

	it('put the indoor-seating count on its checkbox, small as it is', async () => {
		// 3 against 34 and 56 in this fixture, and around 112 of 3,772 in the
		// real snapshot. The count is doing more work on this checkbox than on
		// the other two: it is what stops a filter that hides almost everything
		// from looking broken.
		render(Home);

		await expect.element(page.getByText('(3)')).toBeInTheDocument();
	});
});

describe('the indoor-seating filter', () => {
	/**
	 * Toggle the checkbox by clicking the element itself.
	 *
	 * `locator.click()` times out here with "element is outside of the viewport",
	 * while reporting the element visible, enabled and stable — because it is.
	 * The filters are one column and each control is at least 60px tall, so the
	 * sixth falls below the fold of the harness's fixed-size iframe, and neither
	 * scrolling it into view nor enlarging the viewport moves that boundary. The
	 * control is fine: it renders correctly and a person scrolls to it.
	 *
	 * A native `.click()` dispatches the same trusted-shaped event the component
	 * listens for, so what is under test — that ticking it sends
	 * `indoor_seating=true` and unticking it sends nothing — is exercised
	 * unchanged.
	 */
	function toggle(): void {
		(page.getByLabelText(/Indoor seating/).element() as HTMLInputElement).click();
	}

	it('asks the API for the spots with a recorded yes', async () => {
		render(Home);

		toggle();
		await expect.element(page.getByText('Allerton Library')).toBeInTheDocument();
		await expect.poll(() => lastRequest().parameters.get('indoor_seating')).toBe('true');
	});

	it('never sends false, which is a filter rather than the absence of one', async () => {
		// The mistake worth guarding. `?indoor_seating=false` selects the spots
		// somebody recorded as having *nowhere* to sit inside -- 13 of them
		// citywide -- so an untick that sent it would narrow the results
		// instead of widening them. The checkbox drops the key instead.
		//
		// Unticking the last filter takes the page back to idle without
		// listing, which is how it loads, so the facets request is what shows
		// the parameter is gone: those are refetched on every filter change.
		render(Home);

		toggle();
		await expect.poll(() => lastRequest().parameters.get('indoor_seating')).toBe('true');

		toggle();
		await expect.poll(() => facetRequests().at(-1)?.parameters.has('indoor_seating')).toBe(false);
		expect(calls.some((call) => call.parameters.get('indoor_seating') === 'false')).toBe(false);
	});
});

describe('typing into the box', () => {
	it('searches once the typing pauses, with nothing submitted', async () => {
		render(Home);

		await box().fill('library');

		await expect.element(page.getByText('Bobst Library')).toBeInTheDocument();
		expect(lastRequest().path).toBe('/api/spots/search');
		expect(lastRequest().parameters.get('q')).toBe('library');
	});

	it('coalesces a burst of keystrokes instead of searching per character', async () => {
		render(Home);

		await box().click();
		await userEvent.keyboard('library');
		await expect.element(page.getByText('Bobst Library')).toBeInTheDocument();

		// Seven characters. An exact count would be a race with the debounce, so
		// this pins down the thing that matters: not one request each.
		const searches = calls.filter((call) => call.path === '/api/spots/search');
		expect(searches.length).toBeLessThanOrEqual(2);
		expect(searches[searches.length - 1].parameters.get('q')).toBe('library');
	});

	it('leaves the caret where it was', async () => {
		// The box is a controlled input: the page owns the value and writes it
		// back on every keystroke. Done carelessly that sends the caret to the
		// end, so a correction typed into the middle of a word comes out
		// scrambled. Nothing above would notice, because `fill` appends.
		render(Home);

		const input = box().element() as HTMLInputElement;
		await box().fill('libary');

		input.setSelectionRange(3, 3);
		await userEvent.keyboard('r');

		expect(input.value).toBe('library');
		expect(input.selectionStart).toBe(4);
	});
});
