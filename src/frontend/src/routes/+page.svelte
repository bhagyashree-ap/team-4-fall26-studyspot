<script lang="ts">
	import { resolve } from '$app/paths';
	import SearchBar from '$lib/SearchBar.svelte';
	import SpotResults from '$lib/SpotResults.svelte';
	import SpotFiltersBar from '$lib/SpotFilters.svelte';
	import { ApiError, DEFAULT_LIMIT, fetchFacets, listSpots, searchSpots } from '$lib/api';
	import type { Facets, SpotFilters, StudySpot } from '$lib/contract';

	type Status = 'idle' | 'searching' | 'loaded' | 'error';

	let status = $state<Status>('idle');
	let query = $state('');
	let spots = $state<StudySpot[]>([]);
	let total = $state(0);
	let hasMore = $state(false);
	let loadingMore = $state(false);
	let errorMessage = $state('');

	let facets = $state<Facets | null>(null);
	let filters = $state<SpotFilters>({});

	/**
	 * The query and filters the shown results came from.
	 *
	 * `query` is what the search box shows, which is not the same thing: the box
	 * can be typed in, or emptied, without being submitted. Paging has to repeat
	 * the request that produced the visible page, and the empty-state message has
	 * to name the query that actually found nothing, so both read this instead.
	 *
	 * `run()` records it when it issues a request rather than when one returns,
	 * which is sound because of the `latestSearch` guard below: only the most
	 * recently issued request is allowed to write results, so it is also the one
	 * that wrote this.
	 */
	let applied = $state<{ query: string; filters: SpotFilters }>({ query: '', filters: {} });

	// The hero fills the viewport until there is something below it to see.
	let searched = $derived(status !== 'idle');

	/**
	 * Keep the filter controls describing the results on screen.
	 *
	 * The counts are promises about what picking a value returns, so they follow
	 * `applied` rather than being fetched once: counted over the whole snapshot
	 * they stop being true the moment anything is narrowing the results, and the
	 * controls go on offering values that now match nothing. The endpoint leaves
	 * each facet's own filter out, so a chosen borough still lists the other
	 * four.
	 *
	 * The cost is one extra request per interaction. Returning results and facets
	 * together would avoid it, which is what a dedicated search engine does in a
	 * single response; two requests is the price of keeping this in Postgres.
	 */
	let latestFacets = 0;

	$effect(() => {
		const snapshot = applied;
		const request = ++latestFacets;

		fetchFacets({ query: snapshot.query || undefined, filters: snapshot.filters })
			.then((loaded) => {
				if (request === latestFacets) facets = loaded;
			})
			// Deliberately keeps whatever is already there. Blanking the controls
			// because one refresh failed would take away the filters mid-use; stale
			// counts beside working controls are the better failure.
			.catch(() => {});
	});

	/**
	 * Each search is tagged so a slow earlier request cannot overwrite a faster
	 * later one. Typing a second query before the first returns is ordinary
	 * behaviour, and without this the results could end up showing the wrong one.
	 */
	let latestSearch = 0;

	/**
	 * How long to wait after a keystroke before searching.
	 *
	 * Long enough that an ordinary word is one request rather than five, short
	 * enough to feel like the results are following the typing.
	 *
	 * The matching is what makes a half-typed word worth sending at all:
	 * `search.py` treats the last word as a prefix, so `bob` reaches Bobst
	 * Library. Before that it reached "The Cafe at Bob" and nothing else.
	 */
	const TYPING_DELAY_MS = 250;

	let typingTimer: ReturnType<typeof setTimeout> | undefined;

	/** Search once the typing stops. */
	function runSoon(): void {
		clearTimeout(typingTimer);
		typingTimer = setTimeout(() => void run(), TYPING_DELAY_MS);
	}

	/** Search now, dropping a keystroke's pending search so it cannot land after. */
	function runNow(): void {
		clearTimeout(typingTimer);
		void run();
	}

	// Nothing should fire after the page is gone.
	$effect(() => () => clearTimeout(typingTimer));

	function describe(error: unknown): string {
		if (error instanceof ApiError) {
			// The database being unavailable is worth saying plainly; everything
			// else is reported in the API's own words.
			if (error.code === 'database_unavailable') {
				return 'The study-spot database is unavailable. Try again shortly.';
			}
			if (error.code === 'network_error') {
				return 'Could not reach StudySpot. Check your connection and try again.';
			}
			return error.message;
		}
		return 'Something went wrong while searching.';
	}

	/**
	 * Run whichever request the current query and filters call for.
	 *
	 * A query ranks; filters alone list. With neither there is nothing to show,
	 * so the page returns to the state it loaded in rather than fetching
	 * everything.
	 */
	async function run(): Promise<void> {
		const search = ++latestSearch;
		const trimmed = query.trim();
		const filtering = Object.keys(filters).length > 0;

		applied = { query: trimmed, filters: { ...filters } };

		if (!trimmed && !filtering) {
			status = 'idle';
			spots = [];
			total = 0;
			hasMore = false;
			return;
		}

		status = 'searching';
		errorMessage = '';

		try {
			const page = trimmed
				? await searchSpots(trimmed, { limit: DEFAULT_LIMIT, filters })
				: await listSpots({ limit: DEFAULT_LIMIT, filters });
			if (search !== latestSearch) return;

			spots = page.items;
			total = page.pagination.total;
			hasMore = page.pagination.has_more;
			status = 'loaded';
		} catch (error) {
			if (search !== latestSearch) return;

			errorMessage = describe(error);
			spots = [];
			total = 0;
			hasMore = false;
			status = 'error';
		}
	}

	/**
	 * Typing searches, once it pauses.
	 *
	 * Submitting is still meaningful: it searches immediately rather than waiting
	 * out the delay, and it is how someone who has cleared the box says so.
	 */
	function handleQueryInput(next: string): void {
		query = next;
		runSoon();
	}

	function handleSearch(submitted: string): void {
		query = submitted;
		runNow();
	}

	function handleFilters(next: SpotFilters, typing = false): void {
		filters = next;

		// A select or a checkbox is a decision and lands at once. The campus
		// box is typed, so it waits the same beat the search box does --
		// otherwise every letter of "New York University" is a request.
		if (typing) runSoon();
		else runNow();
	}

	async function handleShowMore(): Promise<void> {
		if (loadingMore) return;
		const search = latestSearch;
		loadingMore = true;

		try {
			// Deliberately `applied` and not the live controls: this continues the
			// page already on screen, which the box may since have been typed in.
			const page = applied.query
				? await searchSpots(applied.query, {
						limit: DEFAULT_LIMIT,
						offset: spots.length,
						filters: applied.filters
					})
				: await listSpots({
						limit: DEFAULT_LIMIT,
						offset: spots.length,
						filters: applied.filters
					});
			if (search !== latestSearch) return;

			spots = [...spots, ...page.items];
			hasMore = page.pagination.has_more;
		} catch (error) {
			if (search !== latestSearch) return;
			errorMessage = describe(error);
		} finally {
			loadingMore = false;
		}
	}
</script>

<svelte:head>
	<title>StudySpot</title>
	<meta
		name="description"
		content="Discover cafés and other NYC third places where students can meet and study."
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
		<nav aria-label="Main navigation">
			<a class="nav-link" href={resolve('/')}>Explore</a>
			<!-- svelte-ignore a11y_invalid_attribute -->
			<a class="nav-link" href="#">Map</a>
			<!-- svelte-ignore a11y_invalid_attribute -->
			<a class="nav-link" href="#">Saved</a>
			<!-- svelte-ignore a11y_invalid_attribute -->
			<a class="nav-link" href="#">Suggest a spot</a>
			<!-- svelte-ignore a11y_invalid_attribute -->
			<a class="sign-in" href="#">Sign in</a>
		</nav>
	</header>

	<main>
		<section class="hero" class:compact={searched} aria-labelledby="hero-title">
			<div class="copy">
				<p class="eyebrow">New York City</p>
				<h1 id="hero-title">Find a place to study together.</h1>
				<p class="description">A great study session starts with the right spot.</p>
			</div>

			<div class="search-card">
				<SearchBar value={query} onInput={handleQueryInput} onSearch={handleSearch} />
				<div class="search-divider" aria-hidden="true"></div>
				<SpotFiltersBar {facets} {filters} onChange={handleFilters} />
			</div>
		</section>

		<!-- aria-live so a screen reader hears the outcome without moving focus. -->
		<div aria-live="polite">
			{#if status === 'searching'}
				<p class="status">Searching…</p>
			{:else if status === 'error'}
				<p class="status error" role="alert">{errorMessage}</p>
			{:else if status === 'loaded' && spots.length === 0}
				<p class="status">
					{#if applied.query}
						No places match <strong>{applied.query}</strong>. Try a library, a campus, or a
						neighborhood, or clear a filter.
					{:else}
						No places match these filters.
					{/if}
				</p>
			{:else if status === 'loaded'}
				<SpotResults {spots} {total} {hasMore} {loadingMore} onShowMore={handleShowMore} />
			{/if}
		</div>
	</main>
</div>

<style>
	.page {
		min-height: 100vh;
		padding: 0 24px 24px;
	}

	header,
	main {
		width: min(1180px, 100%);
		margin: 0 auto;
	}

	header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		height: 76px;
	}

	.brand {
		display: inline-flex;
		align-items: center;
		gap: 9px;
		color: var(--color-brand-hover);
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

	nav {
		display: flex;
		align-items: center;
		gap: 8px;
	}

	.nav-link,
	.sign-in {
		display: inline-flex;
		min-height: 44px;
		align-items: center;
		justify-content: center;
		padding: 0 14px;
		border: 1px solid #eee9e4;
		border-radius: 999px;
		font-size: 14px;
		font-weight: 650;
		line-height: 1.2;
		background: #fff;
		transition: background-color 150ms ease;
	}

	.nav-link:hover {
		background: #f7f1eb;
	}

	.sign-in {
		min-width: 88px;
		margin-left: 4px;
		border-color: #222;
		color: #fff;
		background: #222;
	}

	.sign-in:hover {
		background: #3a3a3a;
	}

	.nav-link:focus-visible,
	.sign-in:focus-visible {
		outline: 3px solid var(--color-brand-hover);
		outline-offset: 3px;
	}

	.hero {
		display: flex;
		min-height: min(700px, calc(100vh - 100px));
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 36px;
		padding: 72px 48px 88px;
		border-radius: 28px;
		background: #f7f1eb;
		text-align: center;
		transition:
			min-height 240ms ease,
			padding 240ms ease;
	}

	/* Once results exist, the hero stops owning the whole viewport. */
	.hero.compact {
		min-height: 0;
		gap: 32px;
		padding: 48px 48px 56px;
	}

	.hero.compact h1 {
		font-size: clamp(2rem, 4vw, 3rem);
	}

	.hero.compact .description {
		display: none;
	}

	.copy {
		max-width: 760px;
	}

	.search-card {
		width: min(800px, 100%);
		padding: 10px;
		border: 1px solid var(--color-border);
		border-radius: 24px;
		background: #fff;
		box-shadow: 0 16px 44px rgb(34 34 34 / 9%);
		text-align: left;
	}

	.search-divider {
		height: 1px;
		margin: 0 8px;
		background: #eee9e4;
	}

	:global(.search-card form[role='search']) {
		width: 100%;
		border: 0;
		border-radius: 18px;
		background: transparent;
		box-shadow: none;
	}

	:global(.search-card form[role='search'] button) {
		background: var(--color-brand-hover);
	}

	:global(.search-card form[role='search'] button:hover) {
		background: #b50935;
	}

	:global(.search-card .filters) {
		width: 100%;
		margin: 0;
		padding: 12px 0 0;
	}

	.eyebrow {
		margin: 0 0 16px;
		color: var(--color-brand-hover);
		font-size: 12px;
		font-weight: 700;
		letter-spacing: 0.1em;
		text-transform: uppercase;
	}

	h1 {
		margin: 0;
		font-size: clamp(3.2rem, 7vw, 5.75rem);
		font-weight: 750;
		letter-spacing: -0.07em;
		line-height: 0.96;
		transition: font-size 240ms ease;
	}

	.description {
		max-width: 580px;
		margin: 26px auto 0;
		color: var(--color-muted);
		font-size: 17px;
		line-height: 1.6;
	}

	.status {
		width: min(800px, 100%);
		margin: 28px auto 0;
		padding: 24px;
		border: 1px solid var(--color-border);
		border-radius: 20px;
		color: var(--color-muted);
		background: #fff;
		font-size: 15px;
		text-align: center;
	}

	.status.error {
		color: var(--color-brand-hover);
		font-weight: 600;
	}

	.status strong {
		color: var(--color-text);
	}

	@media (max-width: 560px) {
		.page {
			padding: 0 12px 15px;
		}

		header {
			height: auto;
			min-height: 68px;
			flex-wrap: wrap;
			gap: 6px;
			padding: 10px 0;
		}

		nav {
			width: 100%;
			flex-wrap: wrap;
			gap: 2px;
		}

		.nav-link,
		.sign-in {
			min-height: 40px;
			padding: 0 10px;
			font-size: 12px;
		}

		.hero {
			min-height: calc(100vh - 112px);
			gap: 36px;
			padding: 48px 14px;
			border-radius: 24px;
		}

		.hero.compact {
			min-height: 0;
			padding: 36px 16px 40px;
		}

		h1 {
			font-size: clamp(2.5rem, 12vw, 3.5rem);
		}

		.description {
			margin-top: 18px;
			font-size: 15px;
		}

		.search-card {
			padding: 6px;
			border-radius: 20px;
		}
	}
</style>
