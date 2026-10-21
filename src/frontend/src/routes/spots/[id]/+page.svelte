<script lang="ts">
	import { resolve } from '$app/paths';
	import type { StudySpot } from '$lib/contract';
	import { showsCampus } from '$lib/campus';
	import { mapsUrl } from '$lib/maps';
	import { orderByTrunk, routeColour, routeTextColour, STEP_FREE, walkMinutes } from '$lib/subway';
	import type { Nearby } from '$lib/server/snapshot';

	let { data }: { data: { spot: StudySpot; nearby: Nearby[] } } = $props();

	const spot = $derived(data.spot);

	/**
	 * The importer's vocabulary is snake_case because the category belongs to
	 * the data. Presenting it is this page's job, as it is the card's.
	 */
	function readableCategory(category: string): string {
		const words = category.replace(/_/g, ' ');
		return words.charAt(0).toUpperCase() + words.slice(1);
	}

	function place(of: StudySpot): string {
		return of.neighborhood ? `${of.neighborhood}, ${of.borough}` : of.borough;
	}

	/** Rounded, because a metre of precision would be false confidence. */
	function walkingDistance(metres: number): string {
		return metres < 100 ? `${Math.round(metres / 10) * 10} m` : `${Math.round(metres / 50) * 50} m`;
	}

	/** Shown at once; the rest sit behind the disclosure. */
	const SHOWN = 4;

	// The same target the result cards use: a hyperlink that opens the viewer's
	// own maps app, where walking and subway directions are one tap away.
	const directions = $derived(mapsUrl(spot));
</script>

{#snippet option(entry: Nearby)}
	<li>
		<a href={resolve(`/spots/${entry.spot.id}` as '/')}>
			<span class="name">{entry.spot.name}</span>
			<span class="meta">
				{readableCategory(entry.spot.category)} · {walkingDistance(entry.metres)} away
			</span>
		</a>
	</li>
{/snippet}

<svelte:head>
	<title>{spot.name} — StudySpot</title>
	<meta
		name="description"
		content="{spot.name}, {readableCategory(spot.category).toLowerCase()} in {place(spot)}."
	/>
</svelte:head>

<div class="page">
	<header>
		<a class="brand" href={resolve('/')} aria-label="StudySpot home">
			<svg viewBox="0 0 32 32" aria-hidden="true">
				<path d="M7 7.5h18v17H7z"></path>
				<path d="M11 12h10M11 16h10M11 20h6"></path>
			</svg>
			<span>StudySpot</span>
		</a>
	</header>

	<main>
		<a class="back" href={resolve('/')}>← All study spots</a>

		<article>
			<p class="eyebrow">{readableCategory(spot.category)}</p>
			<h1>{spot.name}</h1>
			<p class="where">{place(spot)}</p>

			{#if spot.no_purchase_needed || spot.free_public_wifi}
				<p class="badges">
					{#if spot.no_purchase_needed}
						<span class="badge">No purchase needed</span>
					{/if}
					{#if spot.free_public_wifi}
						<span class="badge">Free public Wi-Fi</span>
					{/if}
				</p>
			{/if}

			<dl>
				{#if spot.address}
					<dt>Address</dt>
					<dd>{spot.address}</dd>
				{/if}

				{#if spot.operator && spot.operator !== spot.name}
					<dt>Run by</dt>
					<dd>{spot.operator}</dd>
				{/if}

				{#if showsCampus(spot)}
					<dt>Nearest campus</dt>
					<!--
						Proximity and never affiliation. Spelled out here rather than
						left to a reader's assumption, because a detail page is where
						someone decides whether they are allowed in.
					-->
					<dd>{spot.university} <span class="note">— nearby, not affiliated</span></dd>
				{/if}

				{#if spot.subway_station && spot.subway_routes && spot.subway_metres !== null}
					<dt>Nearest subway</dt>
					<dd>
						<span class="bullets">
							{#each orderByTrunk(spot.subway_routes.split(' ')) as route (route)}
								<span
									class="bullet"
									style:background={routeColour(route)}
									style:color={routeTextColour(route)}>{route}</span
								>
							{/each}
						</span>
						{walkMinutes(spot.subway_metres)} min walk · {spot.subway_station}
						<span class="note">— {STEP_FREE[spot.subway_step_free ?? 'none']}</span>
					</dd>
				{/if}

				<dt>Cost</dt>
				<dd>
					{#if spot.no_purchase_needed}
						Nothing to sit down.
						<span class="note">About money, not entry: some places still ask who you are.</span>
					{:else}
						A purchase is expected.
					{/if}
				</dd>

				<dt>Wi-Fi</dt>
				<dd>
					{#if spot.free_public_wifi}
						A free public hotspot the city publishes sits within 25 m.
					{:else}
						<!--
							The careful wording the whole contract turns on: false means
							unrecorded, not absent.
						-->
						No free public hotspot is recorded within 25 m.
						<span class="note">That is not the same as having no Wi-Fi.</span>
					{/if}
				</dd>
			</dl>

			<!--
				An absolute URL to Google Maps. resolve() is for this application's
				own routes, and the rule cannot tell that a derived string is
				external.
			-->
			<!-- eslint-disable-next-line svelte/no-navigation-without-resolve -->
			<a class="directions" href={directions} rel="noreferrer noopener" target="_blank">
				Open in Maps ↗
			</a>
		</article>

		{#if data.nearby.length > 0}
			<section aria-labelledby="nearby-title">
				<h2 id="nearby-title">Also within a short walk</h2>

				<ul>
					{#each data.nearby.slice(0, SHOWN) as entry (entry.spot.id)}
						{@render option(entry)}
					{/each}
				</ul>

				{#if data.nearby.length > SHOWN}
					<!--
						A native <details>, not a scripted toggle. These pages are
						prerendered and ship no behaviour of their own, so this opens
						for a reader whose JavaScript never arrives.
					-->
					<details>
						<summary>See {data.nearby.length - SHOWN} more options nearby</summary>
						<ul>
							{#each data.nearby.slice(SHOWN) as entry (entry.spot.id)}
								{@render option(entry)}
							{/each}
						</ul>
					</details>
				{/if}
			</section>
		{/if}
	</main>
</div>

<style>
	.page {
		min-height: 100vh;
		padding: 0 24px 64px;
	}

	header,
	main {
		width: min(760px, 100%);
		margin: 0 auto;
	}

	header {
		display: flex;
		align-items: center;
		height: 76px;
	}

	.brand {
		display: inline-flex;
		align-items: center;
		gap: 9px;
		color: var(--color-brand);
		font-size: 20px;
		font-weight: 750;
		letter-spacing: -0.04em;
	}

	.brand svg {
		width: 30px;
		height: 30px;
		fill: none;
		stroke: currentColor;
		stroke-linecap: round;
		stroke-linejoin: round;
		stroke-width: 2;
	}

	.back {
		display: inline-block;
		margin-bottom: 24px;
		color: var(--color-muted);
		font-size: 14px;
		font-weight: 600;
	}

	.back:hover {
		color: var(--color-text);
	}

	article {
		padding: 32px;
		border: 1px solid var(--color-border);
		border-radius: 20px;
		background: white;
	}

	.eyebrow {
		margin: 0 0 10px;
		color: var(--color-brand-hover);
		font-size: 12px;
		font-weight: 700;
		letter-spacing: 0.1em;
		text-transform: uppercase;
	}

	h1 {
		margin: 0;
		font-size: clamp(1.8rem, 4vw, 2.6rem);
		font-weight: 750;
		letter-spacing: -0.04em;
		line-height: 1.1;
	}

	.where {
		margin: 10px 0 0;
		color: var(--color-muted);
		font-size: 15px;
	}

	.badges {
		display: flex;
		flex-wrap: wrap;
		gap: 8px;
		margin: 20px 0 0;
	}

	.badge {
		padding: 6px 12px;
		border-radius: 999px;
		color: var(--color-brand-hover);
		background: #fff1f4;
		font-size: 13px;
		font-weight: 650;
	}

	dl {
		margin: 28px 0 0;
		padding: 24px 0 0;
		border-top: 1px solid var(--color-border);
	}

	dt {
		margin-top: 18px;
		font-size: 12px;
		font-weight: 700;
		letter-spacing: 0.04em;
		text-transform: uppercase;
	}

	dt:first-child {
		margin-top: 0;
	}

	dd {
		margin: 6px 0 0;
		font-size: 15px;
		line-height: 1.55;
	}

	.bullets {
		display: inline-flex;
		gap: 3px;
		vertical-align: -3px;
	}

	.bullet {
		display: inline-flex;
		width: 18px;
		height: 18px;
		align-items: center;
		justify-content: center;
		border-radius: 50%;
		font-size: 11px;
		font-weight: 700;
		line-height: 1;
	}

	.note {
		color: var(--color-muted);
		font-size: 13px;
	}

	.directions {
		display: inline-block;
		min-height: 44px;
		margin-top: 28px;
		padding: 12px 20px;
		border: 1px solid var(--color-border);
		border-radius: 12px;
		font-size: 15px;
		font-weight: 650;
		transition: border-color 160ms ease;
	}

	.directions:hover {
		border-color: var(--color-text);
	}

	section {
		margin-top: 40px;
	}

	h2 {
		margin: 0 0 16px;
		font-size: 17px;
		font-weight: 700;
		letter-spacing: -0.02em;
	}

	ul {
		display: grid;
		gap: 10px;
		margin: 0;
		padding: 0;
		list-style: none;
	}

	li a {
		display: flex;
		flex-wrap: wrap;
		align-items: baseline;
		justify-content: space-between;
		gap: 4px 16px;
		padding: 16px 20px;
		border: 1px solid var(--color-border);
		border-radius: 14px;
		background: white;
		transition: border-color 160ms ease;
	}

	li a:hover {
		border-color: var(--color-text);
	}

	.name {
		font-size: 15px;
		font-weight: 650;
	}

	.meta {
		color: var(--color-muted);
		font-size: 13px;
	}

	details {
		margin-top: 10px;
	}

	summary {
		display: inline-flex;
		min-height: 44px;
		align-items: center;
		color: var(--color-muted);
		cursor: pointer;
		font-size: 14px;
		font-weight: 600;
		list-style: none;
	}

	/* Safari still draws its own marker through `list-style: none`. */
	summary::-webkit-details-marker {
		display: none;
	}

	summary::after {
		margin-left: 7px;
		content: '▾';
		font-size: 11px;
		transition: transform 160ms ease;
	}

	details[open] summary::after {
		transform: rotate(180deg);
	}

	summary:hover {
		color: var(--color-text);
	}

	details ul {
		margin-top: 10px;
	}

	@media (max-width: 560px) {
		.page {
			padding: 0 15px 40px;
		}

		article {
			padding: 24px 20px;
		}
	}
</style>
