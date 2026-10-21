<script lang="ts">
	import { resolve } from '$app/paths';
	import type { StudySpot } from './contract';
	import type { Nearby } from './server/snapshot';

	let { spot, nearby }: { spot: StudySpot; nearby: Nearby[] } = $props();

	/**
	 * The basemap, in this project's own bucket behind its own CloudFront.
	 *
	 * Root-relative on purpose: the tiles are served from the same origin as
	 * the page, so the browser needs no CORS preflight and nothing is fetched
	 * from a third party to draw this.
	 */
	const TILES = '/tiles/nyc.pmtiles';

	let canvas = $state<HTMLDivElement | null>(null);
	let failed = $state(false);

	/**
	 * MapLibre is about 250 KB, and these pages otherwise ship no JavaScript at
	 * all. So it is imported only when the map scrolls into view, and never on
	 * the server: the prerendered HTML is complete without it, and a reader who
	 * does not scroll this far never pays for it.
	 */
	$effect(() => {
		const element = canvas;
		if (element === null) return;

		let map: { remove: () => void } | null = null;
		let cancelled = false;

		const observer = new IntersectionObserver(
			(entries) => {
				if (!entries.some((entry) => entry.isIntersecting)) return;
				observer.disconnect();
				void start();
			},
			{ rootMargin: '200px' }
		);

		async function start(): Promise<void> {
			try {
				const [maplibre, pmtiles] = await Promise.all([
					import('maplibre-gl'),
					import('pmtiles'),
					import('maplibre-gl/dist/maplibre-gl.css')
				]);
				const { basemapStyle } = await import('./basemap');
				const workerUrl = await import('maplibre-gl/dist/maplibre-gl-worker.mjs?url');
				if (cancelled) return;

				/**
				 * MapLibre finds its worker by resolving `maplibre-gl-worker.mjs`
				 * against its own `import.meta.url`. Bundled into a hashed chunk
				 * that resolves to a file Vite never emitted, so every tile
				 * arrived and nothing parsed it -- markers drawn over a blank
				 * map, with "Worker failed to load" in the console.
				 *
				 * `?url` makes Vite emit the worker as an asset and hand back
				 * its real path. The file is self-contained, so nothing has to
				 * resolve once it loads.
				 */
				maplibre.setWorkerUrl(workerUrl.default);

				// Teaches MapLibre to read `pmtiles://` URLs by HTTP range
				// request. Registered per mount; re-registering is harmless.
				maplibre.addProtocol('pmtiles', new pmtiles.Protocol().tile);

				const instance = new maplibre.Map({
					container: element!,
					style: basemapStyle(new URL(TILES, location.href).href),
					center: [spot.longitude, spot.latitude],
					zoom: 15.4,
					attributionControl: { compact: true },
					// Nothing here depends on tilting or spinning, and both make a
					// small locator map harder to read.
					pitchWithRotate: false,
					dragRotate: false,
					touchZoomRotate: false
				});
				map = instance;

				instance.addControl(new maplibre.NavigationControl({ showCompass: false }), 'top-right');

				for (const entry of nearby) {
					const link = document.createElement('a');
					link.className = 'pin';
					link.href = resolve(`/spots/${entry.spot.id}` as '/');
					link.title = `${entry.spot.name} — ${Math.round(entry.metres)} m away`;
					link.setAttribute('aria-label', link.title);
					new maplibre.Marker({ element: link })
						.setLngLat([entry.spot.longitude, entry.spot.latitude])
						.addTo(instance);
				}

				// Added last so it paints above the others.
				const here = document.createElement('div');
				here.className = 'pin here';
				here.setAttribute('aria-hidden', 'true');
				new maplibre.Marker({ element: here })
					.setLngLat([spot.longitude, spot.latitude])
					.addTo(instance);
			} catch {
				// A blocked script, an offline reader, a tile fetch that times
				// out. The list below is the answer either way, so the map
				// simply does not appear.
				if (!cancelled) failed = true;
			}
		}

		observer.observe(element);

		return () => {
			cancelled = true;
			observer.disconnect();
			map?.remove();
		};
	});
</script>

{#if !failed}
	<!--
		aria-hidden because every pin on it is also a link in the list below,
		and announcing each place twice helps nobody. The map is the visual
		route to the same information, not a second set of it.
	-->
	<div class="map" bind:this={canvas} aria-hidden="true"></div>
{/if}

<style>
	.map {
		overflow: hidden;
		height: 260px;
		margin: 0 0 16px;
		border: 1px solid var(--color-border);
		border-radius: 16px;
		background: #f1eeea;
	}

	/*
		:global because MapLibre owns these nodes -- they are created in script
		and appended into the map's own container, so Svelte's scoping never
		reaches them.
	*/
	.map :global(.pin) {
		display: block;
		width: 13px;
		height: 13px;
		border: 2px solid white;
		border-radius: 50%;
		background: var(--color-brand-hover);
		box-shadow: 0 1px 4px rgb(0 0 0 / 30%);
		cursor: pointer;
	}

	.map :global(.pin.here) {
		width: 19px;
		height: 19px;
		border-width: 3px;
		background: var(--color-brand);
		cursor: default;
	}

	.map :global(.maplibregl-ctrl-attrib) {
		font-size: 10px;
	}

	@media (prefers-reduced-motion: reduce) {
		.map :global(.maplibregl-marker) {
			transition: none;
		}
	}
</style>
