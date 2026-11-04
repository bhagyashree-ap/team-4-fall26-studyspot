<script lang="ts">
	import { untrack } from 'svelte';
	import type { Map as MapLibreMap, Marker } from 'maplibre-gl';

	import { resolve } from '$app/paths';

	import { boundsOf, contains, type Bounds } from './bounds';
	import { place, readableCategory } from './spot';
	import type { StudySpot } from './contract';

	type Props = {
		spots: StudySpot[];
		/** Called when the map cannot be drawn, so the caller can list instead. */
		onUnavailable?: () => void;
	};

	let { spots, onUnavailable }: Props = $props();

	/**
	 * The basemap, in this project's own bucket behind its own CloudFront.
	 *
	 * Root-relative on purpose: the tiles are served from the same origin as
	 * the page, so the browser needs no CORS preflight and nothing is fetched
	 * from a third party to draw this. In development there is no archive on
	 * disk, so `vite.config.ts` proxies this prefix to the deployed site.
	 */
	const TILES = '/tiles/nyc.pmtiles';

	/**
	 * Framing limits.
	 *
	 * The zoom cap is what stops a single result -- a rectangle of zero size --
	 * from framing to the tightest zoom the tiles have, which puts one pin in
	 * the middle of a blank block. The padding keeps the outermost pins clear
	 * of the edges and of the zoom control.
	 */
	const MAX_ZOOM = 16;
	const PADDING = 56;

	/** Where to look when there is nothing to frame. Lower Manhattan. */
	const FALLBACK: Bounds = [
		[-74.02, 40.7],
		[-73.96, 40.75]
	];

	let canvas = $state<HTMLDivElement | null>(null);

	/** The map and the module that made it, once both exist. */
	let ready = $state<{ maplibre: typeof import('maplibre-gl'); map: MapLibreMap } | null>(null);

	/**
	 * What a pin says when it is opened: the name, as a link to the detail
	 * page, and where the place is.
	 *
	 * Built as nodes with `textContent` rather than as an HTML string, because
	 * the text is a place name out of open data and `setHTML` would run
	 * whatever a name happened to contain.
	 */
	function popupContent(spot: StudySpot): HTMLElement {
		const wrapper = document.createElement('div');
		wrapper.className = 'popup';

		const link = document.createElement('a');
		link.className = 'name';
		link.href = resolve(`/spots/${spot.id}` as '/');
		link.textContent = spot.name;

		const where = document.createElement('p');
		where.className = 'where';
		where.textContent = `${readableCategory(spot.category)} · ${place(spot)}`;

		wrapper.append(link, where);
		return wrapper;
	}

	/**
	 * Build the map once, on mount.
	 *
	 * MapLibre is about 250 KB and this page otherwise ships little, so it is
	 * imported only when this component mounts -- which only happens when
	 * someone chooses the map view.
	 *
	 * This reads `canvas` and nothing else reactive: `spots` is read through
	 * `untrack` so that a new search adds and removes pins rather than
	 * destroying and rebuilding the map.
	 */
	$effect(() => {
		const element = canvas;
		if (element === null) return;

		const initial = untrack(() => boundsOf(spots));

		let cancelled = false;
		let map: MapLibreMap | null = null;

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
				 * against its own `import.meta.url`, which after bundling is a
				 * hashed chunk directory holding no such file. `?url` makes Vite
				 * emit the worker as an asset and hand back its real path. Same
				 * reasoning as `NearbyMap.svelte`, where this was first found.
				 */
				maplibre.setWorkerUrl(workerUrl.default);

				// Teaches MapLibre to read `pmtiles://` URLs by HTTP range
				// request. Registered per mount; re-registering is harmless.
				maplibre.addProtocol('pmtiles', new pmtiles.Protocol().tile);

				const instance = new maplibre.Map({
					container: element!,
					style: basemapStyle(new URL(TILES, location.href).href),
					// Framed at construction so the first paint is already over
					// the results, rather than flying there a frame later.
					bounds: initial ?? FALLBACK,
					fitBoundsOptions: { padding: PADDING, maxZoom: MAX_ZOOM },
					attributionControl: { compact: true },
					pitchWithRotate: false,
					dragRotate: false,
					touchPitch: false,
					/**
					 * The map is tall and sits in a page that scrolls, so a wheel
					 * over it was zooming the map instead of moving the page --
					 * scrolling past the results meant skidding to a halt and
					 * zooming out to the whole eastern seaboard.
					 *
					 * This hands the wheel back to the page unless ctrl (or cmd)
					 * is held, and asks for two fingers on a touch screen.
					 * MapLibre says so on the map the first time it catches one,
					 * and the zoom buttons are there regardless.
					 */
					cooperativeGestures: true
				});
				map = instance;

				// Pinch to zoom stays -- this is the primary view of the results
				// on a phone -- but turning the map is only ever an accident,
				// and a tilted basemap with no labels is harder to read.
				instance.touchZoomRotate.disableRotation();

				instance.addControl(new maplibre.NavigationControl({ showCompass: false }), 'top-right');

				ready = { maplibre, map: instance };
			} catch {
				// A blocked script, an offline reader, a tile archive that does
				// not answer. The caller falls back to the list, which is the
				// same results by another route.
				if (!cancelled) onUnavailable?.();
			}
		}

		void start();

		return () => {
			cancelled = true;
			ready = null;
			map?.remove();
		};
	});

	/**
	 * Keep the pins equal to the results.
	 *
	 * Re-runs whenever `spots` changes, which is what makes the map and the
	 * list the same set of places: both render this one array, so there is no
	 * second copy to fall out of step.
	 */
	let framed = false;

	$effect(() => {
		const current = spots;
		const loaded = ready;
		if (loaded === null) return;

		const { maplibre, map } = loaded;
		const markers: Marker[] = [];

		// In result order, so tabbing through the pins goes down the ranking
		// rather than wandering around the map.
		for (const spot of current) {
			const pin = document.createElement('button');
			pin.type = 'button';
			pin.className = 'pin';
			// The name alone: the popup carries the rest, and a pin that read
			// out its category and neighbourhood would say it all twice.
			pin.setAttribute('aria-label', spot.name);
			pin.setAttribute('aria-expanded', 'false');

			const popup = new maplibre.Popup({ offset: 15, maxWidth: '260px' }).setDOMContent(
				popupContent(spot)
			);

			// MapLibre opens and closes the popup itself -- on the pin, on a
			// click elsewhere, on the close button -- so the pin's state is
			// read back off the popup rather than tracked alongside it.
			popup.on('open', () => pin.setAttribute('aria-expanded', 'true'));
			popup.on('close', () => pin.setAttribute('aria-expanded', 'false'));

			markers.push(
				new maplibre.Marker({ element: pin })
					.setLngLat([spot.longitude, spot.latitude])
					.setPopup(popup)
					.addTo(map)
			);
		}

		const bounds = boundsOf(current);
		if (bounds !== null) {
			const view = map.getBounds();
			const shown: Bounds = [
				[view.getWest(), view.getSouth()],
				[view.getEast(), view.getNorth()]
			];

			// Only when they would not all be visible. Otherwise "Show more"
			// would re-frame the map under someone who had just panned it to
			// the block they care about.
			if (!framed || !contains(shown, bounds)) {
				map.fitBounds(bounds, { padding: PADDING, maxZoom: MAX_ZOOM });
			}
			framed = true;
		}

		return () => {
			for (const marker of markers) marker.remove();
		};
	});
</script>

<div class="map" bind:this={canvas}></div>

<style>
	.map {
		position: relative;
		overflow: hidden;
		height: clamp(380px, 68vh, 640px);
		border: 1px solid var(--color-border);
		border-radius: 18px;
		background: #f1eeea;
	}

	/*
		:global throughout, because MapLibre owns these nodes -- the pins are
		created in script and appended into the map's own container, and the
		popup is the library's own markup, so Svelte's scoping never reaches
		either.
	*/
	.map :global(.pin) {
		display: block;
		width: 15px;
		height: 15px;
		padding: 0;
		border: 2px solid white;
		border-radius: 50%;
		background: var(--color-brand);
		box-shadow: 0 1px 4px rgb(0 0 0 / 30%);
		cursor: pointer;
		transition:
			transform 120ms ease,
			background-color 120ms ease;
	}

	.map :global(.pin:hover) {
		background: var(--color-brand-hover);
		transform: scale(1.25);
	}

	/* The open pin, so it is clear which one the popup belongs to. */
	.map :global(.pin[aria-expanded='true']) {
		background: var(--color-brand-hover);
		transform: scale(1.35);
	}

	.map :global(.pin:focus-visible) {
		outline: 3px solid var(--color-brand-hover);
		outline-offset: 2px;
	}

	.map :global(.maplibregl-popup-content) {
		padding: 12px 30px 12px 14px;
		border: 1px solid var(--color-border);
		border-radius: 12px;
		box-shadow: 0 8px 24px rgb(34 34 34 / 14%);
	}

	.map :global(.popup .name) {
		font-size: 15px;
		font-weight: 700;
		line-height: 1.3;
		text-decoration: underline;
	}

	.map :global(.popup .where) {
		margin: 4px 0 0;
		color: var(--color-muted);
		font-size: 13px;
	}

	.map :global(.maplibregl-ctrl-attrib) {
		font-size: 10px;
	}

	@media (prefers-reduced-motion: reduce) {
		.map :global(.pin) {
			transition: none;
		}

		.map :global(.maplibregl-marker) {
			transition: none;
		}
	}
</style>
