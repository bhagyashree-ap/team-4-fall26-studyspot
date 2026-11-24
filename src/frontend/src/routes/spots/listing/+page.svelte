<script lang="ts">
	import { page } from '$app/state';
	import { resolve } from '$app/paths';
	import SiteHeader from '$lib/SiteHeader.svelte';
	import SpotDetail from '$lib/SpotDetail.svelte';
	import { ApiError } from '$lib/api';
	import type { StudySpot } from '$lib/contract';

	type Detail = { kind: 'loading' | 'missing' | 'error' } | { kind: 'ready'; spot: StudySpot };
	let request: AbortController | undefined;
	let detail = $state<Detail>({ kind: 'loading' });

	$effect(() => {
		const id = page.url.searchParams.get('id');
		void loadListing(id);
		return () => request?.abort();
	});

	async function loadListing(id: string | null): Promise<void> {
		request?.abort();
		if (!id?.startsWith('listing:')) {
			detail = { kind: 'missing' };
			return;
		}
		request = new AbortController();
		const { signal } = request;
		detail = { kind: 'loading' };
		try {
			const response = await fetch(`/api/spots/${encodeURIComponent(id)}`, { signal });
			if (!response.ok) throw new ApiError('error', 'Listing unavailable.', response.status);
			const spot: StudySpot = await response.json();
			if (!signal.aborted) detail = { kind: 'ready', spot };
		} catch (error) {
			if (!signal.aborted)
				detail = { kind: error instanceof ApiError && error.status === 404 ? 'missing' : 'error' };
		}
	}
</script>

<svelte:head>
	{#if detail.kind !== 'ready'}<title>Study spot · StudySpot</title>{/if}
</svelte:head>

{#if detail.kind === 'ready'}
	<SpotDetail spot={detail.spot} />
{:else}
	<div class="page">
		<SiteHeader />
		<main>
			<a href={resolve('/')}>← All study spots</a>
			{#if detail.kind === 'loading'}
				<p role="status">Loading study spot…</p>
			{:else if detail.kind === 'missing'}
				<h1>Study spot not found</h1>
			{:else}
				<h1>Could not load this study spot</h1>
				<button type="button" onclick={() => loadListing(page.url.searchParams.get('id'))}>
					Try again
				</button>
			{/if}
		</main>
	</div>
{/if}

<style>
	.page {
		padding: 0 24px 32px;
	}
	main {
		width: min(720px, 100%);
		margin: 32px auto;
	}
	main a {
		color: var(--color-brand-hover);
	}
	main p,
	h1 {
		margin: 20px 0;
	}
	button {
		min-height: 44px;
		padding: 0 16px;
		border: 1px solid var(--color-border);
		border-radius: 999px;
		background: white;
		cursor: pointer;
	}
</style>
