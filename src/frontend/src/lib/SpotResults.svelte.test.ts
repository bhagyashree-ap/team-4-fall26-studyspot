/**
 * What a result card does not say.
 *
 * The card briefly carried a Quiet/Moderate/Busy label, then a count of the
 * other spots within 400 m. Both came from the same number, and that number
 * counts *places, not people* -- nothing in open data knows whether a cafe has
 * a free table. The label inferred a conclusion the data could not support,
 * and the count restated the list the card already sits in.
 *
 * So the card says neither. This holds that line, because the pull to put a
 * lively-looking word back on a card is a strong one.
 */

import { page } from 'vitest/browser';
import { describe, expect, it } from 'vitest';
import { render } from 'vitest-browser-svelte';

import SpotResults from './SpotResults.svelte';
import type { StudySpot } from './contract';

const SPOT: StudySpot = {
	id: 'facdb:bobst',
	name: 'Bobst Library',
	category: 'academic_library',
	address: '70 Washington Square South, New York, NY 10012',
	neighborhood: 'Greenwich Village',
	borough: 'Manhattan',
	latitude: 40.72925,
	longitude: -73.99712,
	university: 'New York University',
	operator: 'New York University',
	free_public_wifi: true,
	no_purchase_needed: false,
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

describe('a result card', () => {
	it('shows what it knows about the place', async () => {
		render(SpotResults, { spots: [SPOT], total: 1, hasMore: false });

		await expect.element(page.getByText('Bobst Library')).toBeInTheDocument();
		await expect.element(page.getByText(/W 4 St-Wash Sq/)).toBeInTheDocument();
	});

	it('draws no conclusion about how busy the place is', async () => {
		render(SpotResults, { spots: [SPOT], total: 1, hasMore: false });

		await expect.element(page.getByText('Bobst Library')).toBeInTheDocument();
		await expect.element(page.getByText(/Quiet|Moderate|Busy/)).not.toBeInTheDocument();
	});

	it('does not count the places around it', async () => {
		// nearby_spots is 41 above. The detail page lists those neighbours by
		// name, which is actionable; a bare number on a card in a list of
		// alternatives is not.
		render(SpotResults, { spots: [SPOT], total: 1, hasMore: false });

		await expect.element(page.getByText('Bobst Library')).toBeInTheDocument();
		await expect.element(page.getByText(/41|alternatives?|nearby/i)).not.toBeInTheDocument();
	});
});

describe('the card as a link', () => {
	/** What the browser would actually hit at the centre of `element`. */
	function topmostAt(element: Element): Element | null {
		const box = element.getBoundingClientRect();
		return document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2);
	}

	it('names the detail page on the title', async () => {
		render(SpotResults, { spots: [SPOT], total: 1, hasMore: false });

		const link = page.getByRole('link', { name: 'Bobst Library' });
		await expect.element(link).toBeInTheDocument();
		expect(link.element().getAttribute('href')).toContain('facdb:bobst');
	});

	it('opens the detail page from anywhere in the card body', async () => {
		// The clickable area is a stretched ::after on the title's anchor, so
		// the browser reports that anchor as the hit target over the address
		// line. Asserted by hit-testing rather than by reading the CSS,
		// because what matters is what a click actually lands on.
		render(SpotResults, { spots: [SPOT], total: 1, hasMore: false });

		const address = page.getByText(/70 Washington Square South/);
		await expect.element(address).toBeInTheDocument();

		const hit = topmostAt(address.element());
		expect(hit?.closest('a')?.getAttribute('href')).toContain('facdb:bobst');
	});

	it('leaves Share clickable above that overlay', async () => {
		// The regression this guards: the overlay covers the whole card, so
		// without a raised action row it would swallow Maps and Share.
		render(SpotResults, { spots: [SPOT], total: 1, hasMore: false });

		const share = page.getByRole('button', { name: /Share/ });
		await expect.element(share).toBeInTheDocument();

		const hit = topmostAt(share.element());
		expect(share.element().contains(hit)).toBe(true);
	});

	it('leaves Maps pointing at Google rather than the detail page', async () => {
		render(SpotResults, { spots: [SPOT], total: 1, hasMore: false });

		const maps = page.getByRole('link', { name: /Maps/ });
		await expect.element(maps).toBeInTheDocument();

		const hit = topmostAt(maps.element());
		expect(hit?.closest('a')?.getAttribute('href')).toContain('google.com/maps');
	});
});

describe('the indoor-seating badge', () => {
	/**
	 * Three states, and only one of them is a badge.
	 *
	 * `indoor_seating` is true, false, or unrecorded, and the card has room for
	 * the good news only — so the test that matters is not that a true shows a
	 * badge, it is that a *recorded no* and an *unrecorded* both show nothing
	 * and are never confused with each other. A truthiness check would pass the
	 * first test here and fail the second two silently.
	 */
	it('appears when somebody has recorded somewhere to sit inside', async () => {
		render(SpotResults, {
			spots: [{ ...SPOT, indoor_seating: true }],
			total: 1,
			hasMore: false
		});

		await expect.element(page.getByText('Indoor seating')).toBeInTheDocument();
	});

	it('does not appear when somebody has recorded that there is nowhere', async () => {
		render(SpotResults, {
			spots: [{ ...SPOT, indoor_seating: false }],
			total: 1,
			hasMore: false
		});

		await expect.element(page.getByText('Bobst Library')).toBeInTheDocument();
		await expect.element(page.getByText('Indoor seating')).not.toBeInTheDocument();
	});

	it('does not appear when nobody has recorded it, which is most places', async () => {
		// About 112 spots of 3,772 carry a true. Padding that by inferring
		// seating from anything else is exactly what this field is not for.
		render(SpotResults, { spots: [{ ...SPOT, indoor_seating: null }], total: 1, hasMore: false });

		await expect.element(page.getByText('Bobst Library')).toBeInTheDocument();
		await expect.element(page.getByText('Indoor seating')).not.toBeInTheDocument();
	});

	it('says nothing about the venue’s own Wi-Fi, which the card has no room for', async () => {
		// venue_wifi and free_public_wifi are different claims, and a card that
		// showed both would have to explain the difference in the space of a
		// badge. The detail page does that instead.
		render(SpotResults, {
			spots: [{ ...SPOT, venue_wifi: false, free_public_wifi: true }],
			total: 1,
			hasMore: false
		});

		await expect.element(page.getByText('Free public Wi-Fi')).toBeInTheDocument();
		await expect.element(page.getByText(/no Wi-Fi|Wi-Fi for customers/i)).not.toBeInTheDocument();
	});
});

describe('switching between the list and the map', () => {
	const OTHER: StudySpot = {
		...SPOT,
		id: 'facdb:tamiment',
		name: 'Tamiment Library',
		address: '70 Washington Square South, New York, NY 10012'
	};

	it('offers both views and says which one is showing', async () => {
		render(SpotResults, { spots: [SPOT], total: 1, hasMore: false, view: 'list' });

		const list = page.getByRole('button', { name: 'List' });
		const map = page.getByRole('button', { name: 'Map' });

		await expect.element(list).toBeInTheDocument();
		expect(list.element().getAttribute('aria-pressed')).toBe('true');
		expect(map.element().getAttribute('aria-pressed')).toBe('false');
	});

	it('asks the page to switch rather than switching by itself', async () => {
		// The choice is held a level up so that it survives the next search.
		// A component that flipped its own state would look right in this test
		// and reset itself the moment someone typed another query.
		let asked: string | null = null;
		render(SpotResults, {
			spots: [SPOT],
			total: 1,
			hasMore: false,
			view: 'list',
			onView: (next) => (asked = next)
		});

		await page.getByRole('button', { name: 'Map' }).click();
		expect(asked).toBe('map');
	});

	it('shows the cards in list view and the pins in map view', async () => {
		render(SpotResults, { spots: [SPOT], total: 1, hasMore: false, view: 'map' });

		// The pin is a button named for the place; the card's title is a link.
		await expect.element(page.getByRole('button', { name: 'Bobst Library' })).toBeInTheDocument();
		await expect.element(page.getByRole('link', { name: 'Bobst Library' })).not.toBeInTheDocument();
	});

	/**
	 * The acceptance criterion the two views exist to satisfy. One array feeds
	 * both, so neither can show a set the other does not -- which is why the
	 * assertion is about the count rather than about reconciling two lists.
	 */
	it('counts the places it was given in list view', async () => {
		render(SpotResults, { spots: [SPOT, OTHER], total: 2, hasMore: false, view: 'list' });

		await expect.element(page.getByText('2 places')).toBeInTheDocument();
	});

	it('counts the same places in map view', async () => {
		render(SpotResults, { spots: [SPOT, OTHER], total: 2, hasMore: false, view: 'map' });

		await expect.element(page.getByText('2 places')).toBeInTheDocument();
		// And draws one pin for each of them.
		await expect.element(page.getByRole('button', { name: 'Bobst Library' })).toBeInTheDocument();
		await expect
			.element(page.getByRole('button', { name: 'Tamiment Library' }))
			.toBeInTheDocument();
	});

	it('keeps Show more in map view, because more results are more pins', async () => {
		render(SpotResults, {
			spots: [SPOT],
			total: 40,
			hasMore: true,
			view: 'map'
		});

		await expect.element(page.getByRole('button', { name: 'Show more' })).toBeInTheDocument();
		await expect.element(page.getByText('Showing 1 of 40 places')).toBeInTheDocument();
	});
});
