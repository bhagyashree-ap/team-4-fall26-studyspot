<script lang="ts">
	import { resolve } from '$app/paths';

	import { showsCampus } from './campus';
	import { mapsUrl } from './maps';
	import { orderByTrunk, routeColour, routeTextColour, walkMinutes } from './subway';
	import type { StudySpot } from './contract';

	type Props = {
		spots: StudySpot[];
		total: number;
		hasMore: boolean;
		loadingMore?: boolean;
		onShowMore?: () => void;
	};

	let { spots, total, hasMore, loadingMore = false, onShowMore }: Props = $props();

	/**
	 * The spot whose link was just copied, so one card can say so without the
	 * others claiming it too.
	 */
	let copied = $state<string | null>(null);
	let clearing: ReturnType<typeof setTimeout> | undefined;

	// Nothing should fire after the list is gone.
	$effect(() => () => clearTimeout(clearing));

	/**
	 * Share a spot: the system sheet where there is one, the clipboard where
	 * there is not.
	 *
	 * The link is the detail page, which is prerendered, so whoever receives it
	 * opens real HTML rather than a shell that has to fetch before it can show
	 * anything.
	 */
	async function share(spot: StudySpot): Promise<void> {
		const url = new URL(resolve(`/spots/${spot.id}` as '/'), location.href).href;
		const payload = { title: spot.name, text: `${spot.name} — StudySpot`, url };

		if (navigator.share && navigator.canShare?.(payload)) {
			try {
				await navigator.share(payload);
			} catch {
				// Dismissing the sheet rejects, which is not a failure.
			}
			return;
		}

		try {
			await navigator.clipboard.writeText(url);
			copied = spot.id;
			clearTimeout(clearing);
			clearing = setTimeout(() => (copied = null), 2000);
		} catch {
			// Blocked clipboard, or an insecure context. Saying nothing beats
			// claiming a copy that did not happen.
		}
	}

	/**
	 * The importer's vocabulary is snake_case (`academic_library`), because the
	 * category belongs to the data rather than to the interface. Presenting it
	 * is this component's job, not the API's.
	 */
	function readableCategory(category: string): string {
		const words = category.replace(/_/g, ' ');
		return words.charAt(0).toUpperCase() + words.slice(1);
	}

	/**
	 * Neighborhood is absent for some records and borough never is, so the two
	 * are joined only when both exist rather than leaving a stray separator.
	 */
	function place(spot: StudySpot): string {
		return spot.neighborhood ? `${spot.neighborhood}, ${spot.borough}` : spot.borough;
	}
</script>

<section aria-label="Search results">
	<p class="count">
		{#if total === spots.length}
			{total} {total === 1 ? 'place' : 'places'}
		{:else}
			Showing {spots.length} of {total} places
		{/if}
	</p>

	<ul>
		{#each spots as spot (spot.id)}
			<li>
				<h3>
					<!--
						Every detail page is prerendered, so this is a real document
						rather than a route the browser has to assemble: the link
						works on a fresh tab, in a shared message, and to a crawler.
					-->
					<a href={resolve(`/spots/${spot.id}` as '/')}>{spot.name}</a>
				</h3>
				<p class="meta">
					<span class="category">{readableCategory(spot.category)}</span>
					<span aria-hidden="true">·</span>
					<span>{place(spot)}</span>
				</p>
				{#if spot.address}
					<p class="address">{spot.address}</p>
				{/if}
				{#if spot.operator && spot.operator !== spot.name}
					<!--
						Who runs it, which for a library branch is its system. Worth
						showing because the three systems have separate membership,
						and a branch's own name never says which one it belongs to.

						Hidden when it merely repeats the name, which is what FacDB
						stores for the academic and special libraries.
					-->
					<p class="operator">{spot.operator}</p>
				{/if}
				{#if spot.subway_station && spot.subway_routes && spot.subway_metres !== null}
					<!--
						Which trains, then how long the walk. Lines are coloured
						because people read the colour faster than the letter, and
						the walk is in minutes because nobody converts 409 m.
					-->
					<p class="subway">
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
					</p>
				{/if}

				{#if showsCampus(spot)}
					<!-- Proximity, never affiliation: see the contract. -->
					<p class="campus">Near {spot.university}</p>
				{/if}
				{#if spot.no_purchase_needed || spot.free_public_wifi}
					<!--
						Both are shown only when true, and for the same reason: the
						absence of one is not evidence of its opposite. A false
						free_public_wifi means no hotspot the city publishes sits
						within 25 m, which is not the same as no Wi-Fi, and saying
						"no Wi-Fi" would assert more than the data supports.
					-->
					<p class="badges">
						{#if spot.no_purchase_needed}
							<!--
								Money, not entry. A campus building costs nothing and
								still wants the university's credentials, which is why
								this does not say "open to all".
							-->
							<span class="badge">
								<svg viewBox="0 0 24 24" aria-hidden="true">
									<path d="M3.5 12.3V5.2a1.7 1.7 0 0 1 1.7-1.7h7.1l8.2 8.2-8.8 8.8-8.2-8.2Z" />
									<circle cx="8" cy="8" r="1.1" />
								</svg>
								No purchase needed
							</span>
						{/if}
						{#if spot.free_public_wifi}
							<span class="badge">
								<svg viewBox="0 0 24 24" aria-hidden="true">
									<path d="M5 12.5a10 10 0 0 1 14 0" />
									<path d="M8.5 16a5 5 0 0 1 7 0" />
									<circle cx="12" cy="19.5" r="1" />
								</svg>
								Free public Wi-Fi
							</span>
						{/if}
					</p>
				{/if}

				<p class="actions">
					<!--
						A link, not an embedded map: it opens the viewer's own maps app with
						the place pinned, where walking and subway directions are one tap
						away. Nothing is loaded from anyone else to render this card.
					-->
					<!-- eslint-disable-next-line svelte/no-navigation-without-resolve -->
					<a class="maps" href={mapsUrl(spot)} rel="noreferrer noopener" target="_blank">
						<svg viewBox="0 0 24 24" aria-hidden="true">
							<path d="M12 21s7-6.2 7-11a7 7 0 1 0-14 0c0 4.8 7 11 7 11Z" />
							<circle cx="12" cy="10" r="2.4" />
						</svg>
						Maps
					</a>

					<button type="button" onclick={() => share(spot)}>
						{#if copied === spot.id}
							<svg viewBox="0 0 24 24" aria-hidden="true">
								<path d="m5 12.5 4.5 4.5L19 7.5" />
							</svg>
							Copied
						{:else}
							<svg viewBox="0 0 24 24" aria-hidden="true">
								<path d="M12 16V4m0 0L7.5 8.5M12 4l4.5 4.5" />
								<path d="M4.5 14v4.5a1.5 1.5 0 0 0 1.5 1.5h12a1.5 1.5 0 0 0 1.5-1.5V14" />
							</svg>
							Share
						{/if}
					</button>
				</p>
			</li>
		{/each}
	</ul>

	{#if hasMore}
		<button type="button" onclick={() => onShowMore?.()} disabled={loadingMore}>
			{loadingMore ? 'Loading…' : 'Show more'}
		</button>
	{/if}
</section>

<style>
	section {
		width: min(1180px, 100%);
		margin: 0 auto;
		padding: 40px 0 72px;
		text-align: left;
	}

	.count {
		margin: 0 0 20px;
		color: var(--color-muted);
		font-size: 14px;
		font-weight: 600;
	}

	ul {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
		gap: 16px;
		margin: 0;
		padding: 0;
		list-style: none;
	}

	/*
		`position: relative` is what lets the title's stretched ::after cover
		the card. Everything below depends on it.
	*/
	li {
		position: relative;
		display: flex;
		flex-direction: column;
		padding: 20px;
		border: 1px solid var(--color-border);
		border-radius: 18px;
		background: white;
		transition:
			border-color 160ms ease,
			box-shadow 160ms ease,
			transform 160ms ease;
	}

	/*
		A ring rather than a drop shadow: `0 0 0 3px` spreads with no offset and
		no blur beneath the card, so the card is outlined, not elevated on a
		smudge. The lift is the only thing that moves.
	*/
	li:hover,
	li:has(a:focus-visible) {
		border-color: var(--color-brand);
		box-shadow: 0 0 0 3px rgb(255 56 92 / 0.18);
		transform: translateY(-2px);
	}

	/*
		The whole card opens the detail page, but the <a> stays wrapped around
		the title only: an anchor may not contain a button, and the Share
		button is one. So the title's ::after is stretched over the card
		instead, which keeps one real link per card -- focusable, openable in a
		new tab, and announced by its name rather than by "card".
	*/
	h3 a::after {
		position: absolute;
		border-radius: 18px;
		content: '';
		inset: 0;
	}

	li:hover h3 a {
		text-decoration: underline;
	}

	.meta {
		display: flex;
		flex-wrap: wrap;
		gap: 7px;
		margin: 0;
		color: var(--color-muted);
		font-size: 13px;
	}

	.category {
		color: var(--color-brand-hover);
		font-weight: 650;
	}

	.subway {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 4px 7px;
		margin: 10px 0 0;
		color: var(--color-muted);
		font-size: 13px;
	}

	.bullets {
		display: inline-flex;
		gap: 3px;
	}

	.bullet {
		display: inline-flex;
		width: 17px;
		height: 17px;
		align-items: center;
		justify-content: center;
		border-radius: 50%;
		font-size: 11px;
		font-weight: 700;
		line-height: 1;
	}

	.address,
	.operator,
	.campus {
		margin: 10px 0 0;
		color: var(--color-muted);
		font-size: 13px;
		line-height: 1.5;
	}

	.campus {
		font-style: italic;
	}

	.badges {
		display: flex;
		flex-wrap: wrap;
		gap: 6px 14px;
		margin: 10px 0 0;
	}

	.badge {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		color: var(--color-brand-hover);
		font-size: 13px;
		font-weight: 650;
	}

	.badge svg {
		width: 15px;
		flex: none;
		fill: none;
		stroke: currentColor;
		stroke-linecap: round;
		stroke-linejoin: round;
		stroke-width: 2;
	}

	/*
		`auto` on the top margin, not a fixed 14px: the cards are grid items and
		stretch to the tallest in their row, so a fixed margin left this row
		floating at a different height in every card. An address that wraps to
		two lines is enough to break the line-up.
	*/
	.actions {
		position: relative;
		z-index: 1;
		display: flex;
		gap: 10px;
		margin: 18px 0 0;
		margin-top: auto;
		padding-top: 14px;
		border-top: 1px solid var(--color-border);
	}

	.maps {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		min-height: 34px;
		padding: 0 14px;
		border: 1px solid var(--color-border);
		border-radius: 10px;
		font-size: 13px;
		font-weight: 650;
		transition: border-color 160ms ease;
	}

	/*
		The margin reset matters: the "Show more" rule below sets
		`margin: 28px auto 0`, which also matched this button and pushed it 28px
		down and `auto` across — the two sat at different heights and drifted
		apart.
	*/
	.actions button {
		display: inline-flex;
		min-height: 34px;
		margin: 0;
		align-items: center;
		gap: 6px;
		padding: 0 14px;
		border: 1px solid var(--color-border);
		border-radius: 10px;
		background: white;
		font-size: 13px;
		font-weight: 650;
		cursor: pointer;
		transition: border-color 160ms ease;
	}

	.actions button:hover {
		border-color: var(--color-text);
	}

	.actions button svg {
		width: 15px;
		fill: none;
		stroke: currentColor;
		stroke-linecap: round;
		stroke-linejoin: round;
		stroke-width: 2;
	}

	.maps:hover {
		border-color: var(--color-text);
	}

	.maps svg {
		width: 15px;
		fill: none;
		stroke: currentColor;
		stroke-linecap: round;
		stroke-linejoin: round;
		stroke-width: 2;
	}

	button {
		display: block;
		min-height: 48px;
		margin: 28px auto 0;
		padding: 0 28px;
		border: 1px solid var(--color-border);
		border-radius: 12px;
		background: white;
		font-size: 15px;
		font-weight: 650;
		cursor: pointer;
		transition: border-color 160ms ease;
	}

	button:hover:not(:disabled) {
		border-color: var(--color-text);
	}

	button:disabled {
		color: var(--color-muted);
		cursor: progress;
	}

	@media (max-width: 560px) {
		ul {
			grid-template-columns: 1fr;
		}
	}
</style>
