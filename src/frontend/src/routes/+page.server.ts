import { neighborhoodsByBorough } from '$lib/server/snapshot';
import type { PageServerLoad } from './$types';

// Runs once at build time, like the detail pages' loader: `+page.ts` keeps
// `prerender = true`, so the list is written into the static page and its
// `__data.json` and nothing serves it at runtime. It must not read the URL,
// which a prerendered load cannot.
export const load: PageServerLoad = () => ({ neighborhoods: neighborhoodsByBorough() });
