/**
 * The results map.
 *
 * MapLibre draws onto a canvas, and a test cannot read a canvas. What it can
 * read is the part that matters here: the pins are real buttons and the popup
 * is real markup, both in the document, which is also what makes them
 * reachable by keyboard and by a screen reader.
 *
 * The basemap itself does not load -- there is no tile archive in front of the
 * test server, and `vite.config.ts` only proxies one in development. That is
 * fine, and deliberate: a pin is placed from a spot's own coordinates, not
 * from anything the tiles say, so every assertion below holds over an empty
 * basemap.
 */

import { page } from 'vitest/browser';
import { describe, expect, it } from 'vitest';
import { render } from 'vitest-browser-svelte';

import ResultsMap from './ResultsMap.svelte';
import type { StudySpot } from './contract';

function spot(id: string, name: string, latitude: number, longitude: number): StudySpot {
	return {
		id,
		name,
		category: 'academic_library',
		address: null,
		neighborhood: 'Greenwich Village',
		borough: 'Manhattan',
		latitude,
		longitude,
		university: 'New York University',
		operator: null,
		free_public_wifi: true,
		no_purchase_needed: true,
		subway_station: null,
		subway_routes: null,
		subway_metres: null,
		subway_step_free: null,
		nearby_spots: 0,
		outdoor_seating: false,
		indoor_seating: null,
		venue_wifi: null,
		opening_hours: null
	};
}

const BOBST = spot('facdb:bobst', 'Bobst Library', 40.72925, -73.99712);
const TAMIMENT = spot('facdb:tamiment', 'Tamiment Library', 40.7294, -73.9969);

describe('a pin for every result', () => {
	it('puts one on the map for each spot', async () => {
		render(ResultsMap, { spots: [BOBST, TAMIMENT] });

		await expect.element(page.getByRole('button', { name: 'Bobst Library' })).toBeInTheDocument();
		await expect
			.element(page.getByRole('button', { name: 'Tamiment Library' }))
			.toBeInTheDocument();
	});

	it('names each one, so a pin is not an unlabelled dot', async () => {
		// Pins are buttons rather than decoration: they can be tabbed to, and
		// what they announce is the place they stand for.
		render(ResultsMap, { spots: [BOBST] });

		const pin = page.getByRole('button', { name: 'Bobst Library' });
		await expect.element(pin).toBeInTheDocument();
		expect(pin.element().tagName).toBe('BUTTON');
	});

	it('orders them by rank, not by position on the map', async () => {
		// Tabbing through the pins should go down the result list. Insertion
		// order is what decides it, so this holds that order.
		render(ResultsMap, { spots: [BOBST, TAMIMENT] });

		await expect.element(page.getByRole('button', { name: 'Bobst Library' })).toBeInTheDocument();

		const names = [...document.querySelectorAll('.pin')].map((pin) =>
			pin.getAttribute('aria-label')
		);
		expect(names).toEqual(['Bobst Library', 'Tamiment Library']);
	});
});

describe('opening a pin', () => {
	it('shows the name as a link to the detail page', async () => {
		render(ResultsMap, { spots: [BOBST] });

		const pin = page.getByRole('button', { name: 'Bobst Library' });
		await expect.element(pin).toBeInTheDocument();
		await pin.click();

		// The name *is* the link, which is how the card does it too: one
		// target, named by the place rather than by "view details".
		const link = page.getByRole('link', { name: 'Bobst Library' });
		await expect.element(link).toBeInTheDocument();
		expect(link.element().getAttribute('href')).toContain('/spots/facdb:bobst');
	});

	it('says where the place is', async () => {
		render(ResultsMap, { spots: [BOBST] });

		const pin = page.getByRole('button', { name: 'Bobst Library' });
		await expect.element(pin).toBeInTheDocument();
		await pin.click();

		await expect
			.element(page.getByText('Academic library · Greenwich Village, Manhattan'))
			.toBeInTheDocument();
	});

	it('marks the pin as open, and closed again after', async () => {
		render(ResultsMap, { spots: [BOBST] });

		const pin = page.getByRole('button', { name: 'Bobst Library' });
		await expect.element(pin).toBeInTheDocument();

		expect(pin.element().getAttribute('aria-expanded')).toBe('false');

		await pin.click();
		await expect.element(page.getByRole('link', { name: 'Bobst Library' })).toBeInTheDocument();
		expect(pin.element().getAttribute('aria-expanded')).toBe('true');

		await pin.click();
		await expect.element(page.getByRole('link', { name: 'Bobst Library' })).not.toBeInTheDocument();
		expect(pin.element().getAttribute('aria-expanded')).toBe('false');
	});

	it('writes the name as text, never as markup', async () => {
		// Place names come out of open data. `setHTML` would run whatever one
		// of them happened to contain.
		const injected = spot('facdb:x', '<img src=x onerror="window.ran=1">', 40.73, -73.99);
		render(ResultsMap, { spots: [injected] });

		const pin = page.getByRole('button', { name: injected.name });
		await expect.element(pin).toBeInTheDocument();
		await pin.click();

		await expect.element(page.getByText(injected.name)).toBeInTheDocument();
		expect(document.querySelector('.popup img')).toBeNull();
	});
});
