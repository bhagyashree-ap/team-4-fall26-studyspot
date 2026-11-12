/**
 * Where "Near me" gets a point from, and what the neighborhood picker lists.
 */

import type { Borough } from './contract';

/** One `<optgroup>` of the neighborhood picker. */
export type NeighborhoodGroup = {
	borough: Borough;
	neighborhoods: string[];
};

/**
 * What asking the browser for a position came to.
 *
 * The three failures are kept apart because the reader can do something
 * different about each: a refusal is undone in the browser's site settings, an
 * unsupported browser never will work, and a timeout may work on a second try.
 */
export type Located =
	| { kind: 'found'; latitude: number; longitude: number }
	| { kind: 'denied' }
	| { kind: 'unavailable' }
	| { kind: 'unsupported' };

/**
 * Coarse and cached on purpose. Ordering a city's study spots needs the block,
 * not the metre, and high accuracy can mean waiting for a GPS fix indoors.
 */
export const LOCATE_OPTIONS: PositionOptions = {
	enableHighAccuracy: false,
	timeout: 10_000,
	maximumAge: 5 * 60_000
};

/**
 * Ask for the reader's position once.
 *
 * `geolocation` is passed in rather than read from `navigator`, so the caller
 * owns the browser dependency and a test can hand over a fake. It is
 * `undefined` where the browser has no Geolocation API at all.
 */
export function locate(geolocation: Geolocation | undefined): Promise<Located> {
	if (geolocation === undefined) return Promise.resolve({ kind: 'unsupported' });

	return new Promise((settle) => {
		geolocation.getCurrentPosition(
			(position) =>
				settle({
					kind: 'found',
					latitude: position.coords.latitude,
					longitude: position.coords.longitude
				}),
			(failure) =>
				// Insecure origins are refused with PERMISSION_DENIED too, which is
				// right: the remedy is the same, the browser will not say where.
				settle({ kind: failure.code === failure.PERMISSION_DENIED ? 'denied' : 'unavailable' }),
			LOCATE_OPTIONS
		);
	});
}
