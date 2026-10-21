/**
 * Which spots name a nearby campus.
 *
 * The field is proximity, never affiliation. These pin the places where
 * showing it would say something the data does not support.
 */

import { describe, expect, it } from 'vitest';

import { showsCampus } from './campus';

function spot(category: string, university: string | null) {
	return { category, university };
}

describe('naming a nearby campus', () => {
	it('shows it for a cafe, where it orients a reader', () => {
		expect(showsCampus(spot('cafe', 'New York University'))).toBe(true);
	});

	it('shows it for a public library, for the same reason', () => {
		expect(showsCampus(spot('public_library', 'Columbia University'))).toBe(true);
	});

	it('hides it for an academic library, which is already on a campus', () => {
		// "Elmer Holmes Bobst Library — Near New York University" repeats the
		// name and adds nothing.
		expect(showsCampus(spot('academic_library', 'New York University'))).toBe(false);
	});

	it('hides it for a university building', () => {
		expect(showsCampus(spot('university_building', 'New York University'))).toBe(false);
	});

	it('hides the two that would be wrong rather than merely redundant', () => {
		// Real rows. "New York University Libraries" is nearest to Long Island
		// University's Brooklyn campus, and the NYPL's research libraries are
		// nearest to Berkeley College. Both true as distance, both read as
		// affiliation.
		expect(showsCampus(spot('academic_library', 'LIU-New York University Campus'))).toBe(false);
		expect(showsCampus(spot('academic_library', 'Berkeley College - Main Campus'))).toBe(false);
	});

	it('hides it when there is no campus within range', () => {
		expect(showsCampus(spot('cafe', null))).toBe(false);
	});
});
