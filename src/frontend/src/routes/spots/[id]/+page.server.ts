import { error } from '@sveltejs/kit';

import { allSpots, nearbySpots, spotById } from '$lib/server/snapshot';
import type { EntryGenerator, PageServerLoad } from './$types';

// Every detail page is written as real HTML at build time. The identifiers come
// from the committed snapshot, so the set is known in advance and no route is
// left to a runtime fallback.
export const prerender = true;

export const entries: EntryGenerator = () => allSpots().map((spot) => ({ id: spot.id }));

export const load: PageServerLoad = ({ params }) => {
	const spot = spotById(params.id);
	if (spot === undefined) {
		// Unreachable through `entries`, and the honest answer if the snapshot
		// and a hand-typed URL ever disagree.
		throw error(404, `No study spot has the identifier ${params.id}`);
	}

	// Twelve rather than four: the page shows four and keeps the rest behind a
	// disclosure. The median spot has 39 neighbours inside 800 m and the busiest
	// has 178, so this is a cap, not a complete list -- and it is a cap on bytes
	// written into 1,915 prerendered pages as much as on what a reader can use.
	return { spot, nearby: nearbySpots(spot, 12) };
};
