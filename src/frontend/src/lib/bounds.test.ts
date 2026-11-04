/**
 * Framing arithmetic for the results map.
 */

import { describe, expect, it } from 'vitest';

import { boundsOf, contains, type Bounds } from './bounds';

/** Only the two fields `boundsOf` reads. */
function at(latitude: number, longitude: number) {
	return { latitude, longitude };
}

describe('the bounds of a set of spots', () => {
	it('is nothing at all when there are no spots', () => {
		// The map has nothing to frame, which the caller has to distinguish from
		// a rectangle of zero size around one spot.
		expect(boundsOf([])).toBeNull();
	});

	it('is a point for a single spot', () => {
		expect(boundsOf([at(40.72925, -73.99712)])).toEqual([
			[-73.99712, 40.72925],
			[-73.99712, 40.72925]
		]);
	});

	it('holds every spot given to it', () => {
		// Bobst in the Village, the Brooklyn central library, and a Bronx
		// branch: far enough apart that a mistaken min or max would show.
		const bounds = boundsOf([
			at(40.72925, -73.99712),
			at(40.6724, -73.9681),
			at(40.8679, -73.8757)
		]);

		expect(bounds).toEqual([
			[-73.99712, 40.6724],
			[-73.8757, 40.8679]
		]);
	});

	it('puts west before east and south before north', () => {
		// The order MapLibre's fitBounds takes. Swapping a pair frames the
		// wrong rectangle without erroring, so it is worth pinning.
		const bounds = boundsOf([at(40.6, -74.1), at(40.9, -73.7)]) as Bounds;
		const [[west, south], [east, north]] = bounds;

		expect(west).toBeLessThan(east);
		expect(south).toBeLessThan(north);
	});
});

describe('whether a view already holds the pins', () => {
	const view: Bounds = [
		[-74, 40.6],
		[-73.9, 40.8]
	];

	it('is true when the pins are inside it', () => {
		expect(
			contains(view, [
				[-73.98, 40.65],
				[-73.95, 40.75]
			])
		).toBe(true);
	});

	it('is true when a pin sits exactly on the edge', () => {
		// It is on screen, so it is not a reason to move the map.
		expect(
			contains(view, [
				[-74, 40.6],
				[-73.9, 40.8]
			])
		).toBe(true);
	});

	it('is false when a pin falls outside, in any direction', () => {
		const outside: Bounds[] = [
			[
				[-74.2, 40.65],
				[-73.95, 40.75]
			],
			[
				[-73.98, 40.65],
				[-73.8, 40.75]
			],
			[
				[-73.98, 40.5],
				[-73.95, 40.75]
			],
			[
				[-73.98, 40.65],
				[-73.95, 40.95]
			]
		];

		for (const pins of outside) expect(contains(view, pins)).toBe(false);
	});
});
