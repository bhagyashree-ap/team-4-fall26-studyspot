<script lang="ts">
	import { onDestroy } from 'svelte';
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { SvelteURLSearchParams } from 'svelte/reactivity';
	import SiteHeader from '$lib/SiteHeader.svelte';
	import { communityRequest } from '$lib/communities';
	import { searchSpots } from '$lib/api';
	import { session } from '$lib/session.svelte';
	import { locate } from '$lib/near';
	import type { StudySpot } from '$lib/contract';
	type Spot = Pick<StudySpot, 'id' | 'name' | 'address' | 'neighborhood' | 'borough'>;
	type Person = {
		username: string;
		display_name: string;
		school?: string;
		courses?: string[];
		topics?: string[];
		study_spot?: { id: string; name: string } | null;
		distance_metres?: number;
	};
	let people = $state<Person[]>([]);
	let query = $state('');
	let course = $state('');
	let topic = $state('');
	let selectedSpot = $state<Spot | null>(null);
	let spotQuery = $state('');
	let suggestions = $state<Spot[]>([]);
	let status = $state('');
	let busy = $state(false);
	let searched = $state(false);
	let hasMore = $state(false);
	let lastLocation = $state<{ latitude: number; longitude: number } | null>(null);
	let firstSearchStarted = $state(false);
	let loadingMore = $state(false);
	let latestSearch = 0;
	let timer: ReturnType<typeof setTimeout> | undefined;
	let latest = 0;
	onDestroy(() => clearTimeout(timer));
	$effect(() => {
		if (
			session.status === 'signed-in' &&
			session.account?.account_type === 'student' &&
			!firstSearchStarted
		) {
			firstSearchStarted = true;
			void search();
		}
	});

	function findSpot(value: string) {
		spotQuery = value;
		selectedSpot = null;
		suggestions = [];
		clearTimeout(timer);
		const request = ++latest;
		if (value.trim().length < 2) return;
		timer = setTimeout(() => {
			void searchSpots(value.trim(), { limit: 10 })
				.then((response) => {
					if (request === latest) suggestions = response.items;
				})
				.catch(() => {
					if (request === latest) suggestions = [];
				});
		}, 220);
	}

	async function search(location?: { latitude: number; longitude: number }, append = false) {
		const request = ++latestSearch;
		searched = true;
		if (append) loadingMore = true;
		status = 'Searching students…';
		if (!append) lastLocation = location ?? null;
		const effectiveLocation = location ?? (append ? lastLocation : null);
		const parameters = new SvelteURLSearchParams();
		if (query.trim()) parameters.set('q', query.trim());
		if (course.trim()) parameters.set('course', course.trim());
		if (topic.trim()) parameters.set('topic', topic.trim());
		if (selectedSpot) parameters.set('spot', selectedSpot.id);
		if (effectiveLocation) {
			parameters.set('latitude', String(effectiveLocation.latitude));
			parameters.set('longitude', String(effectiveLocation.longitude));
		}
		if (append) parameters.set('offset', String(people.length));
		try {
			const response = await communityRequest<{ items: Person[]; has_more: boolean }>(
				`/people${parameters.size ? `?${parameters}` : ''}`
			);
			if (request !== latestSearch) return;
			people = append ? [...people, ...response.items] : response.items;
			hasMore = response.has_more;
			status = people.length
				? ''
				: 'No matching students found. Try a different course, topic, or study spot.';
		} catch (error) {
			if (request === latestSearch)
				status = error instanceof Error ? error.message : 'Could not search students.';
		} finally {
			if (request === latestSearch) loadingMore = false;
		}
	}

	async function nearMe() {
		busy = true;
		const result = await locate(navigator.geolocation);
		if (result.kind === 'found') await search(result);
		else status = 'Location is unavailable. Allow location access, or search by study spot.';
		busy = false;
	}

	async function message(person: Person) {
		try {
			const response = await communityRequest<{ id: number }>(
				`/people/${encodeURIComponent(person.username)}/dm`,
				'POST',
				{}
			);
			await goto(resolve(`/messages?dm=${response.id}`));
		} catch (error) {
			status = error instanceof Error ? error.message : 'Could not start a conversation.';
		}
	}
</script>

<svelte:head
	><title>People · StudySpot</title><meta
		name="description"
		content="Find students to study with."
	/></svelte:head
>
<main class="people-page">
	<SiteHeader />
	<section class="intro">
		<p class="eyebrow">STUDY TOGETHER</p>
		<h1>Find your study people.</h1>
		<p>Search registered students by course, study topic, or study spot.</p>
	</section>
	{#if session.status === 'signed-in' && session.account?.account_type === 'student'}
		<section class="panel" aria-labelledby="search-title">
			<h2 id="search-title">Find students</h2>
			<p class="lede">
				Only details a student chose to share appear in results. Usernames are shown so you can find
				registered students.
			</p>
			<form
				class="filters"
				onsubmit={(event) => {
					event.preventDefault();
					void search();
				}}
			>
				<label class="field"
					><span>Name or school</span><input
						bind:value={query}
						placeholder="Search people"
					/></label
				>
				<label class="field"
					><span>Course</span><input bind:value={course} placeholder="e.g. CS 101" /></label
				>
				<label class="field"
					><span>Study topic</span><input
						bind:value={topic}
						placeholder="e.g. machine learning"
					/></label
				>
				<div class="field spot-field">
					<label for="people-spot">Study spot</label><input
						id="people-spot"
						value={spotQuery}
						oninput={(event) => findSpot(event.currentTarget.value)}
						placeholder="Any spot — search by name"
						autocomplete="off"
						role="combobox"
						aria-autocomplete="list"
						aria-expanded={suggestions.length > 0}
						aria-controls="people-spot-options"
					/>
					{#if suggestions.length}<ul
							id="people-spot-options"
							role="listbox"
							aria-label="Study spot matches"
						>
							{#each suggestions as spot (spot.id)}<li>
									<button
										type="button"
										role="option"
										aria-selected="false"
										onclick={() => {
											selectedSpot = spot;
											spotQuery = spot.name;
											suggestions = [];
										}}
										><strong>{spot.name}</strong><span
											>{[spot.neighborhood, spot.borough, spot.address]
												.filter(Boolean)
												.join(' · ')}</span
										></button
									>
								</li>{/each}
						</ul>{/if}
					{#if selectedSpot}<p class="selected">
							Filtering at {selectedSpot.name}<button
								type="button"
								onclick={() => {
									selectedSpot = null;
									spotQuery = '';
								}}>Clear</button
							>
						</p>{/if}
				</div>
				<div class="actions">
					<button class="primary" type="submit">Search</button><button
						class="secondary"
						type="button"
						onclick={nearMe}
						disabled={busy}>{busy ? 'Finding nearby…' : 'Near me'}</button
					>
				</div>
			</form>
			<p class="status" role="status">{status}</p>
			{#if people.length}<div class="results">
					{#each people as person (person.username)}<article class="person">
							<div class="avatar" aria-hidden="true">
								{person.display_name.slice(0, 1).toUpperCase()}
							</div>
							<div class="details">
								<h3>
									<a href={resolve(`/people/${encodeURIComponent(person.username)}`)}
										>{person.display_name}</a
									>
								</h3>
								{#if person.school}<p>{person.school}</p>{/if}{#if person.courses?.length}<p>
										<strong>Courses</strong> · {person.courses.join(', ')}
									</p>{/if}{#if person.topics?.length}<p>
										<strong>Study topics</strong> · {person.topics.join(', ')}
									</p>{/if}{#if person.study_spot}<p>
										<strong>Study spot</strong> · {person.study_spot.name}
									</p>{/if}{#if person.distance_metres !== undefined}<p>
										{person.distance_metres} m from you
									</p>{/if}
							</div>
							<button class="message" type="button" onclick={() => message(person)}>Message</button>
						</article>{/each}
				</div>{/if}
			{#if searched && !people.length && !status}<p class="empty">
					No students match those filters.
				</p>{/if}
			{#if hasMore}<button
					class="secondary more"
					type="button"
					onclick={() => void search(undefined, true)}
					disabled={loadingMore}>{loadingMore ? 'Loading…' : 'Load more students'}</button
				>{/if}
		</section>
	{:else if session.status === 'signed-out'}
		<section class="panel">
			<h2>Sign in to find study partners</h2>
			<p class="lede">People search is available to completed student accounts.</p>
			<button class="primary" onclick={() => session.logIn('/people')}>Log in</button>
		</section>
	{:else if session.status === 'disabled'}
		<section class="panel">
			<h2>Student discovery is unavailable</h2>
			<p class="lede">
				Sign-in is not configured for this local run. Configure the team Auth0 settings to use
				People.
			</p>
		</section>
	{:else if session.status === 'signed-in'}
		<section class="panel">
			<h2>Student accounts only</h2>
			<p class="lede">People search is available to completed student accounts.</p>
		</section>
	{:else}
		<section class="panel"><p class="lede">Loading your student account…</p></section>
	{/if}
</main>

<style>
	.people-page {
		--ink: #292923;
		--muted: #717169;
		--line: #e8e8e1;
		--accent: #555b45;
		--control: #33382c;
		max-width: 1180px;
		margin: 0 auto;
		padding: 0 24px 64px;
		color: var(--ink);
		font-family: Inter, ui-sans-serif, system-ui, sans-serif;
	}
	.intro {
		padding: 44px 0 22px;
	}
	.eyebrow {
		margin: 0 0 8px;
		color: var(--color-brand-hover);
		font-size: 11px;
		font-weight: 750;
		letter-spacing: 0.13em;
	}
	.intro h1 {
		margin: 0;
		font-size: clamp(34px, 5vw, 54px);
		letter-spacing: -0.05em;
		line-height: 1.08;
	}
	.intro > p:last-child {
		margin: 11px 0 0;
		color: var(--muted);
	}
	.panel {
		padding: 38px;
		border: 1px solid #eee9e4;
		border-radius: 28px;
		background: #f7f1eb;
	}
	.panel h2 {
		margin: 0;
		font-size: 24px;
		letter-spacing: -0.03em;
	}
	.lede {
		margin: 7px 0 20px;
		color: var(--muted);
		font-size: 14px;
		line-height: 1.5;
	}
	.filters {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 16px 20px;
		align-items: end;
	}
	.field {
		position: relative;
		display: flex;
		min-width: 0;
		flex-direction: column;
		gap: 7px;
		font-size: 13px;
		font-weight: 650;
	}
	.field input {
		width: 100%;
		min-height: 43px;
		padding: 10px 12px;
		border: 1px solid #ded9d4;
		border-radius: 9px;
		background: white;
		color: var(--ink);
		font: inherit;
		font-size: 14px;
		font-weight: 400;
	}
	.spot-field ul {
		position: absolute;
		z-index: 4;
		top: calc(100% + 2px);
		left: 0;
		right: 0;
		max-height: 280px;
		overflow: auto;
		margin: 0;
		padding: 5px;
		list-style: none;
		border: 1px solid #ded9d4;
		border-radius: 10px;
		background: white;
		box-shadow: 0 12px 28px #28231c20;
	}
	.spot-field li button {
		display: flex;
		width: 100%;
		flex-direction: column;
		gap: 3px;
		padding: 9px 10px;
		border: 0;
		border-radius: 7px;
		background: white;
		color: var(--ink);
		text-align: left;
		cursor: pointer;
	}
	.spot-field li button:hover {
		background: #f7f1eb;
	}
	.spot-field li span {
		color: var(--muted);
		font-size: 11px;
		font-weight: 400;
	}
	.selected {
		margin: 0;
		color: var(--muted);
		font-size: 12px;
	}
	.selected button {
		margin-left: 9px;
		padding: 0;
		border: 0;
		color: var(--color-brand-hover);
		background: transparent;
		cursor: pointer;
	}
	.actions {
		display: flex;
		gap: 9px;
	}
	.primary,
	.secondary,
	.message {
		display: inline-flex;
		min-height: 42px;
		align-items: center;
		justify-content: center;
		padding: 0 18px;
		border: 1px solid transparent;
		border-radius: 999px;
		font: inherit;
		font-size: 13px;
		font-weight: 650;
		cursor: pointer;
	}
	.primary,
	.message {
		color: white;
		background: #222;
	}
	.secondary {
		border-color: #eee9e4;
		color: var(--ink);
		background: #f7f1eb;
	}
	.status {
		min-height: 18px;
		margin: 18px 0 0;
		color: var(--muted);
		font-size: 13px;
	}
	.results {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(min(100%, 360px), 1fr));
		gap: 12px;
		margin-top: 12px;
	}
	.person {
		display: grid;
		grid-template-columns: 42px minmax(0, 1fr) auto;
		align-items: start;
		gap: 12px;
		padding: 16px;
		border: 1px solid var(--line);
		border-radius: 13px;
	}
	.avatar {
		display: grid;
		width: 42px;
		height: 42px;
		place-items: center;
		border-radius: 50%;
		color: #fff;
		background: var(--color-brand-hover);
		font-weight: 700;
	}
	.details h3 {
		margin: 1px 0 7px;
		font-size: 16px;
	}
	.details p {
		margin: 5px 0 0;
		color: var(--muted);
		font-size: 12px;
		line-height: 1.45;
		overflow-wrap: anywhere;
	}
	.details strong {
		color: var(--ink);
	}
	.message {
		min-height: 36px;
		padding: 0 13px;
	}
	.empty {
		color: var(--muted);
		font-size: 14px;
	}
	.more {
		margin-top: 18px;
	}
	@media (max-width: 680px) {
		.people-page {
			padding: 0 16px 42px;
		}
		.intro {
			padding-top: 32px;
		}
		.panel {
			padding: 22px;
			border-radius: 20px;
		}
		.filters {
			grid-template-columns: minmax(0, 1fr);
			gap: 14px;
		}
	}
	@media (max-width: 440px) {
		.people-page {
			padding-right: 12px;
			padding-left: 12px;
		}
		.panel {
			padding: 17px;
		}
		.person {
			grid-template-columns: 38px minmax(0, 1fr);
		}
		.avatar {
			width: 38px;
			height: 38px;
		}
		.message {
			grid-column: 2;
			justify-self: start;
		}
	}
</style>
