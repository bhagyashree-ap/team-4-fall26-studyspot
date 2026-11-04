import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vitest/config';
import { playwright } from '@vitest/browser-playwright';
import staticAdapter from '@sveltejs/adapter-static';
import { sveltekit } from '@sveltejs/kit/vite';

const apiProxyTarget = process.env.API_PROXY_TARGET ?? 'http://localhost:7501';

/**
 * Where the basemap comes from in development.
 *
 * In production the PMTiles archive sits in the site bucket and is served by
 * the same CloudFront distribution as the page, so the browser fetches it
 * same-origin. Nothing builds it into `static/`: it is 31 MB, it changes a few
 * times a year, and committing it would put it in every clone and every
 * deploy.
 *
 * So locally there is no `/tiles` to fetch and the maps simply did not draw.
 * Proxying the prefix to the deployed site fixes that without a copy on disk;
 * range requests pass straight through. `.claude/launch.json` fills this in
 * from `terraform output site_url`.
 */
const tilesProxyTarget = process.env.TILES_PROXY_TARGET;

// One deployment. The app is served as prerendered files from S3 behind
// CloudFront, which needs no server at all because every route sets
// `prerender = true`, so `bun run build` produces the S3 upload directly.
//
// The fallback is 404.html rather than index.html so that a missing key is a
// 404 instead of the homepage served under the wrong URL.
const adapter = staticAdapter({ fallback: '404.html' });

export default defineConfig({
	ssr: { noExternal: ['@lucide/svelte'] },
	plugins: [
		tailwindcss(),
		sveltekit({
			compilerOptions: {
				// Force runes mode for the project, except for libraries. Can be removed in svelte 6.
				runes: ({ filename }) =>
					filename.split(/[/\\]/).includes('node_modules') ? undefined : true
			},
			adapter
		})
	],
	server: {
		proxy: {
			'/api': {
				target: apiProxyTarget,
				changeOrigin: true,
				rewrite: (path) => path.replace(/^\/api/, '')
			},
			...(tilesProxyTarget ? { '/tiles': { target: tilesProxyTarget, changeOrigin: true } } : {})
		}
	},
	test: {
		expect: { requireAssertions: true },
		projects: [
			{
				extends: './vite.config.ts',
				test: {
					name: 'client',
					browser: {
						enabled: true,
						provider: playwright(),
						instances: [{ browser: 'chromium', headless: true }]
					},
					include: ['src/**/*.svelte.{test,spec}.{js,ts}'],
					exclude: ['src/lib/server/**']
				}
			},

			{
				extends: './vite.config.ts',
				test: {
					name: 'server',
					environment: 'node',
					include: ['src/**/*.{test,spec}.{js,ts}'],
					exclude: ['src/**/*.svelte.{test,spec}.{js,ts}']
				}
			}
		]
	}
});
