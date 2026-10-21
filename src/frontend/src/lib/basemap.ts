/**
 * A MapLibre style for the self-hosted NYC basemap.
 *
 * The tiles are one PMTiles archive in this project's own S3 bucket, served by
 * the same CloudFront distribution as the site. There is no tile server, no
 * API key, and nothing billable per view: a reader's browser range-requests
 * the handful of tiles it needs out of a 31 MB file, and CloudFront caches
 * those ranges.
 *
 * **Written by hand, and deliberately without labels.** Protomaps publishes
 * ready-made styles, and every one of them points `glyphs` at
 * `protomaps.github.io`. Using that would mean a reader's browser fetching
 * fonts from someone else's GitHub Pages on every map -- a third party in the
 * render path, for a project that currently has none, and a dependency on
 * hosting nobody here controls.
 *
 * Dropping labels removes the need for glyphs entirely, and for a locator map
 * a few hundred metres across it is the better design anyway: street names at
 * this size are clutter, and the pins are what carry the meaning.
 *
 * Layer ids are the Protomaps v3 schema, confirmed against the extract itself
 * rather than from documentation: boundaries, buildings, earth, landcover,
 * landuse, places, pois, roads, water.
 */

import type { StyleSpecification } from 'maplibre-gl';

/** Muted enough that the pins are the brightest thing on it. */
const PAPER = '#f6f4f2';
const LAND = '#f1eeea';
const GREEN = '#e3ebdf';
const WATER = '#d3e2ec';
const BUILDING = '#e7e2dc';
const ROAD = '#ffffff';
const ROAD_EDGE = '#e2ddd6';

export function basemapStyle(tilesUrl: string): StyleSpecification {
	return {
		version: 8,
		// No glyphs and no sprite: nothing here draws text or icons, so
		// declaring them would only invite a fetch we do not make.
		sources: {
			protomaps: {
				type: 'vector',
				url: `pmtiles://${tilesUrl}`,
				attribution:
					'<a href="https://openstreetmap.org/copyright">OpenStreetMap</a> · <a href="https://protomaps.com">Protomaps</a>'
			}
		},
		layers: [
			{ id: 'background', type: 'background', paint: { 'background-color': PAPER } },
			{
				id: 'earth',
				type: 'fill',
				source: 'protomaps',
				'source-layer': 'earth',
				paint: { 'fill-color': LAND }
			},
			{
				id: 'landuse',
				type: 'fill',
				source: 'protomaps',
				'source-layer': 'landuse',
				filter: ['in', ['get', 'kind'], ['literal', ['park', 'garden', 'forest', 'grass', 'wood']]],
				paint: { 'fill-color': GREEN }
			},
			{
				id: 'water',
				type: 'fill',
				source: 'protomaps',
				'source-layer': 'water',
				paint: { 'fill-color': WATER }
			},
			{
				id: 'buildings',
				type: 'fill',
				source: 'protomaps',
				'source-layer': 'buildings',
				paint: { 'fill-color': BUILDING, 'fill-opacity': 0.9 }
			},
			// Two passes so roads read as roads: a wider muted casing under a
			// white fill, which is what gives them an edge against the buildings.
			{
				id: 'roads-casing',
				type: 'line',
				source: 'protomaps',
				'source-layer': 'roads',
				filter: ['!=', ['get', 'kind'], 'path'],
				layout: { 'line-cap': 'round', 'line-join': 'round' },
				paint: {
					'line-color': ROAD_EDGE,
					'line-width': ['interpolate', ['exponential', 1.6], ['zoom'], 12, 1.5, 16, 7, 19, 26]
				}
			},
			{
				id: 'roads',
				type: 'line',
				source: 'protomaps',
				'source-layer': 'roads',
				filter: ['!=', ['get', 'kind'], 'path'],
				layout: { 'line-cap': 'round', 'line-join': 'round' },
				paint: {
					'line-color': ROAD,
					'line-width': ['interpolate', ['exponential', 1.6], ['zoom'], 12, 0.5, 16, 5, 19, 22]
				}
			}
		]
	};
}
