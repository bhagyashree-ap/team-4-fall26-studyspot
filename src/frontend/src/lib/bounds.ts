/**
 * The rectangle a set of spots occupies, and whether one rectangle holds
 * another.
 *
 * Both are needed to decide when the results map should re-frame itself.
 * Framing on every change would yank the map out from under someone who had
 * just panned it; never framing would leave a new search drawing its pins
 * somewhere off screen. The rule is to re-frame only when the pins do not
 * already fit, which `contains` answers.
 *
 * Kept out of the component because it is arithmetic, and arithmetic is worth
 * testing without a browser or a map in the way.
 */

import type { StudySpot } from './contract';

/**
 * `[[west, south], [east, north]]` -- the order MapLibre's `fitBounds` takes.
 *
 * Longitudes are compared as plain numbers, which is only sound because every
 * spot is in New York City. A set of points spanning the antimeridian has no
 * single min and max longitude, and this would frame the long way round the
 * planet; nothing in this dataset can.
 */
export type Bounds = [[number, number], [number, number]];

type Point = Pick<StudySpot, 'latitude' | 'longitude'>;

/** The smallest rectangle holding every point, or null for no points. */
export function boundsOf(points: Point[]): Bounds | null {
	if (points.length === 0) return null;

	let west = Infinity;
	let south = Infinity;
	let east = -Infinity;
	let north = -Infinity;

	for (const { latitude, longitude } of points) {
		if (longitude < west) west = longitude;
		if (longitude > east) east = longitude;
		if (latitude < south) south = latitude;
		if (latitude > north) north = latitude;
	}

	return [
		[west, south],
		[east, north]
	];
}

/**
 * Whether `inner` lies entirely within `outer`.
 *
 * Inclusive at the edges: a pin exactly on the edge of the view is visible, so
 * it is not a reason to re-frame.
 */
export function contains(outer: Bounds, inner: Bounds): boolean {
	const [[outerWest, outerSouth], [outerEast, outerNorth]] = outer;
	const [[innerWest, innerSouth], [innerEast, innerNorth]] = inner;

	return (
		innerWest >= outerWest &&
		innerEast <= outerEast &&
		innerSouth >= outerSouth &&
		innerNorth <= outerNorth
	);
}
