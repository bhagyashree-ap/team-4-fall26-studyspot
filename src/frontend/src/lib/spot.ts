/**
 * How a spot is worded in the interface.
 *
 * Shared by the result card and the map popup. They name the same places from
 * the same fields, and when the wording lived in the card only, the popup had
 * to repeat it -- two copies that would drift the first time either changed.
 */

import type { StudySpot } from './contract';

/**
 * The importer's vocabulary is snake_case (`academic_library`), because the
 * category belongs to the data rather than to the interface. Presenting it is
 * the interface's job, not the API's.
 */
export function readableCategory(category: string): string {
	const words = category.replace(/_/g, ' ');
	return words.charAt(0).toUpperCase() + words.slice(1);
}

/**
 * Neighborhood is absent for some records and borough never is, so the two are
 * joined only when both exist rather than leaving a stray separator.
 */
export function place(spot: Pick<StudySpot, 'neighborhood' | 'borough'>): string {
	return spot.neighborhood ? `${spot.neighborhood}, ${spot.borough}` : spot.borough;
}

/**
 * A distance from where the reader asked about, for the Near me ordering.
 *
 * Rounded like the detail page's walking distances -- to 10 m under 100 m and
 * 50 m above -- because a metre of precision would be false confidence in a
 * straight-line figure. From a kilometre it switches to km, with one decimal
 * until the decimal stops mattering at 10 km.
 */
export function formatDistance(metres: number): string {
	const rounded = metres < 100 ? Math.round(metres / 10) * 10 : Math.round(metres / 50) * 50;
	if (rounded < 1000) return `${rounded} m`;
	const kilometres = metres / 1000;
	return kilometres < 9.95 ? `${kilometres.toFixed(1)} km` : `${Math.round(kilometres)} km`;
}
