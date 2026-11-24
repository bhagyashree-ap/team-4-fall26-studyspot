<script lang="ts">
	import { resolve } from '$app/paths';
	import { untrack } from 'svelte';
	import { listOwnedListings } from './accounts';
	import { ApiError } from './api';
	import type { StudySpot } from './contract';
	import type { Session, SessionScope } from './session.svelte';
	import { place, spotPath } from './spot';

	let { session }: { session: Session } = $props();
	type Listings = { kind: 'loading' | 'error' } | { kind: 'ready'; items: StudySpot[] };
	let state = $state<Listings>({ kind: 'loading' });
	let request = 0;
	$effect(() => {
		const scope = session.scope;
		if (scope) untrack(() => void load(scope));
		return () => {
			request += 1;
		};
	});

	async function load(scope: SessionScope): Promise<void> {
		const sequence = ++request;
		state = { kind: 'loading' };
		try {
			const credentials = await session.credentialsFor(scope);
			if (sequence !== request || !session.isCurrent(scope)) return;
			const { items } = await listOwnedListings(credentials);
			if (sequence === request && session.isCurrent(scope)) state = { kind: 'ready', items };
		} catch (error) {
			if (sequence !== request || !session.isCurrent(scope)) return;
			if (error instanceof ApiError && error.status === 401) session.rejectCredentials(scope);
			else state = { kind: 'error' };
		}
	}
</script>

<section aria-labelledby="owned-listings-title">
	<h2 id="owned-listings-title">Your listings</h2>
	{#if state.kind === 'loading'}
		<p role="status">Loading your listings…</p>
	{:else if state.kind === 'error'}
		<p role="alert">Could not load your listings.</p>
		<button
			type="button"
			onclick={() => {
				const scope = session.scope;
				if (scope) void load(scope);
			}}
		>
			Try again
		</button>
	{:else if state.kind === 'ready'}
		{#if state.items.length === 0}
			<p>No listings yet.</p>
		{:else}
			<ul>
				{#each state.items as spot (spot.id)}
					<li>
						<a href={resolve(`${spotPath(spot.id)}#reviews` as '/')}>
							<strong>{spot.name}</strong>
							<span>{place(spot)} · Read reviews</span>
						</a>
					</li>
				{/each}
			</ul>
		{/if}
	{/if}
</section>

<style>
	section {
		margin-block: 28px;
	}
	h2 {
		margin-bottom: 8px;
		font-size: 1.125rem;
		font-weight: 700;
	}
	p,
	span {
		color: var(--color-muted);
		font-size: 0.875rem;
	}
	li {
		border-block-start: 1px solid var(--color-border);
	}
	a {
		display: grid;
		gap: 2px;
		padding-block: 12px;
		color: var(--color-brand-hover);
		overflow-wrap: anywhere;
	}
	a:hover strong,
	button:hover {
		text-decoration: underline;
	}
	button {
		min-height: 44px;
		color: var(--color-brand-hover);
		font-weight: 650;
		cursor: pointer;
	}
</style>
