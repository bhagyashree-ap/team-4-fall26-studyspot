/**
 * Whether a spot's nearest campus is worth showing.
 *
 * `university` is the nearest campus within 500 m. It is proximity and never
 * affiliation, which the wording everywhere is careful to say. On a cafe or a
 * public library that is useful orientation: it tells a student whether a
 * place is near where they already are.
 *
 * On a university building or an academic library it is not. The place *is*
 * the campus, so "Near New York University" under "Elmer Holmes Bobst
 * Library" repeats the name and adds nothing.
 *
 * Worse, on exactly those records it reads as a claim about who runs the
 * place, and in two cases in the snapshot that claim would be wrong:
 *
 * - "New York University Libraries" is nearest to `LIU-New York University
 *   Campus`, which is Long Island University in Brooklyn, not NYU.
 * - "NY Public Library Research Libraries" is nearest to `Berkeley College -
 *   Main Campus`, and the NYPL is not an academic library at all.
 *
 * Both are correct as distances and misleading as sentences. Hiding the line
 * where it cannot inform is cheaper than wording around it.
 */

import type { StudySpot } from './contract';

/** Categories that are themselves a campus, so naming a nearby one is noise. */
const CAMPUS_IS_REDUNDANT = new Set(['academic_library', 'university_building']);

export function showsCampus(spot: Pick<StudySpot, 'category' | 'university'>): boolean {
	return spot.university !== null && !CAMPUS_IS_REDUNDANT.has(spot.category);
}
