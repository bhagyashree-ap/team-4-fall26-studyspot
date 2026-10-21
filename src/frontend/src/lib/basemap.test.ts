/**
 * The basemap style.
 *
 * These are mostly about what the style does *not* contain. The map is drawn
 * from one PMTiles archive in this project's own bucket, and the thing most
 * likely to undo that quietly is someone swapping in a ready-made Protomaps
 * style: every published one points `glyphs` at protomaps.github.io, which
 * would put a third party in the render path of every detail page.
 */

import { describe, expect, it } from 'vitest';

import { basemapStyle } from './basemap';

const TILES = 'https://example.test/tiles/nyc.pmtiles';

describe('the basemap style', () => {
	it('reads the archive through the pmtiles protocol', () => {
		// Not an ordinary tile URL: the protocol is what turns a single file
		// into range requests, so a reader fetches kilobytes of a 31 MB archive.
		const source = basemapStyle(TILES).sources.protomaps;
		expect(source).toMatchObject({ type: 'vector', url: `pmtiles://${TILES}` });
	});

	it('fetches nothing from anywhere else', () => {
		const style = basemapStyle(TILES);
		const urls = JSON.stringify(style).match(/https?:\/\/[^"']+/g) ?? [];

		// Attribution links are the exception: they are hrefs a reader may
		// click, not resources the page loads.
		const fetched = urls.filter((url) => !url.includes('openstreetmap.org/copyright'));
		expect(
			fetched.filter((url) => !url.startsWith(TILES) && !url.includes('protomaps.com'))
		).toEqual([]);
	});

	it('declares no glyphs and no sprite', () => {
		// Declaring either would invite a fetch. Nothing in this style draws
		// text or icons, so neither is needed -- which is why there are no
		// labels on the map.
		const style = basemapStyle(TILES) as Record<string, unknown>;
		expect(style.glyphs).toBeUndefined();
		expect(style.sprite).toBeUndefined();
	});

	it('draws no text layer that would need them', () => {
		const kinds = basemapStyle(TILES).layers.map((layer) => layer.type);
		expect(kinds).not.toContain('symbol');
	});

	it('credits OpenStreetMap and Protomaps', () => {
		// ODbL requires it, and the map is unattributed without it.
		const source = basemapStyle(TILES).sources.protomaps as { attribution?: string };
		expect(source.attribution).toContain('OpenStreetMap');
		expect(source.attribution).toContain('Protomaps');
	});

	it('names only layers the extract actually has', () => {
		// Confirmed against `pmtiles show --metadata` on the archive itself. A
		// typo here fails silently: the layer simply never draws.
		const present = new Set([
			'boundaries',
			'buildings',
			'earth',
			'landcover',
			'landuse',
			'places',
			'pois',
			'roads',
			'water'
		]);

		for (const layer of basemapStyle(TILES).layers) {
			const name = (layer as { 'source-layer'?: string })['source-layer'];
			if (name !== undefined) expect(present).toContain(name);
		}
	});
});
