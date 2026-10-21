/**
 * The Maps link.
 *
 * It is the one place a user leaves the application, so the URL has to be
 * right: a wrong query sends someone across the city. These check the shape
 * Google documents and the fallback for the records that have no address.
 */

import { describe, expect, it } from 'vitest';

import type { StudySpot } from './contract';
import { mapsUrl } from './maps';

function spot(overrides: Partial<StudySpot> = {}): StudySpot {
	return {
		id: 'facdb:test',
		name: "Jean's",
		category: 'cafe',
		address: '415 Lafayette Street, New York, NY 10003',
		neighborhood: 'Greenwich Village',
		borough: 'Manhattan',
		latitude: 40.728521,
		longitude: -73.992568,
		university: null,
		operator: null,
		free_public_wifi: false,
		no_purchase_needed: false,
		subway_station: null,
		subway_routes: null,
		subway_metres: null,
		subway_step_free: null,
		nearby_spots: 0,
		outdoor_seating: false,
		indoor_seating: null,
		venue_wifi: null,
		opening_hours: null,
		...overrides
	};
}

describe('the Maps link', () => {
	it('uses the interface Google documents', () => {
		expect(mapsUrl(spot())).toContain('https://www.google.com/maps/search/?api=1&query=');
	});

	it('searches for the name with its address', () => {
		// Lands on the business, with its own hours and photos, rather than on
		// a bare pin labelled with coordinates. The address is what makes the
		// name unambiguous, so this is not the loose text search it resembles.
		const url = mapsUrl(spot());
		expect(decodeURIComponent(url)).toContain("Jean's, 415 Lafayette Street, New York, NY 10003");
	});

	it('falls back to coordinates when there is no address', () => {
		// 36 records in the snapshot have none, and a pin in the right place
		// beats no link.
		const url = mapsUrl(spot({ address: null }));
		expect(decodeURIComponent(url)).toContain('40.728521,-73.992568');
		expect(url).not.toContain('Lafayette');
	});

	it('escapes a name that would otherwise break the query', () => {
		// "100% Coffee" and "Mom & Pop" are both real shapes in this data: an
		// unescaped & would truncate the query at the ampersand.
		const url = mapsUrl(spot({ name: '100% Coffee & Co', address: '1 Test St' }));

		expect(url).not.toContain('& Co');
		expect(url).toContain('%26');
		expect(decodeURIComponent(url)).toContain('100% Coffee & Co, 1 Test St');
	});

	it('produces a link with no key or credential in it', () => {
		// It is a hyperlink, not the Places API: nothing here is billable and
		// nothing needs a secret.
		const url = mapsUrl(spot());
		expect(url).not.toMatch(/key=|token=|apikey/i);
	});
});
