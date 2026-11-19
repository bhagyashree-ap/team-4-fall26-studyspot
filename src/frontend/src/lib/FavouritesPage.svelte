<script lang="ts">
	import { untrack } from 'svelte';
	import { resolve } from '$app/paths';
	import SiteHeader from './SiteHeader.svelte';
	import SpotResults from './SpotResults.svelte';
	import { session } from './session.svelte';
	import { favourites } from './favourites.svelte';

	let view = $state<'list' | 'map'>('list');

	$effect(() => {
		const scope = session.scope;
		if (scope && session.account?.account_type === 'student')
			untrack(() => {
				void favourites.load();
			});
	});
</script>

<div class="page">
	<SiteHeader />
	<main>
		<div class="heading">
			<p class="eyebrow">Your study spots</p>
			<h1>Favourites</h1>
			<p>Private places to come back to, saved by you.</p>
		</div>
		<div class="status" aria-live="polite">
			{#if session.status === 'loading'}
				<p>Loading your account…</p>
			{:else if session.status === 'disabled'}
				<p>Accounts are not switched on for this site.</p>
			{:else if session.status === 'error'}
				<p role="alert">{session.error}</p>
				<a href={resolve('/favourites')} data-sveltekit-reload>Retry</a>
			{:else if session.status === 'signed-out'}
				<p>Log in or sign up with a student account to see your favourites.</p>
				<button type="button" onclick={() => session.logIn('/favourites')}>Log in</button>
				<a href={resolve('/signup?returnTo=%2Ffavourites')}>Sign up</a>
			{:else if session.account?.account_type === null}
				<p>Finish signing up as a student to use favourites.</p>
				<a href={resolve('/account?returnTo=%2Ffavourites')}>Finish sign-up</a>
			{:else if session.account?.account_type === 'business'}
				<p>Favourites are available to student accounts.</p>
			{:else if favourites.status === 'idle' || favourites.status === 'loading'}
				<p>Loading your favourites…</p>
			{:else if favourites.status === 'error'}
				<p role="alert">{favourites.error}</p>
				<button type="button" onclick={() => favourites.load({ refresh: true })}>Retry</button>
			{:else if favourites.items.length === 0}
				<p>No favourites yet. Save a study spot to find it here.</p>
				<a href={resolve('/')}>Explore study spots</a>
			{/if}
		</div>
		{#if session.status === 'signed-in' && session.account?.account_type === 'student' && favourites.items.length > 0}
			<SpotResults
				spots={favourites.items}
				total={favourites.items.length}
				hasMore={false}
				showFavouriteError={false}
				{view}
				onView={(next) => (view = next)}
			/>
		{/if}
	</main>
</div>

<style>
	.page {
		min-height: 100vh;
		padding: 0 24px 32px;
	}
	main {
		width: min(1180px, 100%);
		margin: 0 auto;
	}
	.heading {
		padding: 44px 32px;
		border-radius: 28px;
		background: #f7f1eb;
	}
	.eyebrow {
		color: var(--color-brand-hover);
		font-size: 12px;
		font-weight: 700;
		letter-spacing: 0.1em;
		text-transform: uppercase;
	}
	h1 {
		margin: 8px 0 16px;
		font-size: clamp(2.2rem, 5vw, 3.5rem);
		letter-spacing: -0.06em;
		line-height: 1;
	}
	.heading p:last-child,
	.status {
		color: var(--color-muted);
		line-height: 1.6;
	}
	.status:not(:empty) {
		padding: 24px 0;
	}
	button,
	.status a {
		display: inline-flex;
		min-height: 44px;
		align-items: center;
		margin-right: 8px;
		padding: 0 18px;
		border: 1px solid var(--color-border);
		border-radius: 999px;
		background: white;
		color: var(--color-text);
		font-size: 14px;
		font-weight: 650;
		cursor: pointer;
	}
	button:focus-visible,
	.status a:focus-visible {
		outline: 3px solid var(--color-brand-hover);
		outline-offset: 3px;
	}
	@media (max-width: 560px) {
		.page {
			padding: 0 12px 24px;
		}
		.heading {
			padding: 32px 20px;
		}
	}
</style>
