<script lang="ts">
	import { untrack } from 'svelte';
	import { resolve } from '$app/paths';
	import type { StudySpot } from './contract';
	import { favourites as sharedFavourites, type Favourites } from './favourites.svelte';
	import { session as sharedSession, type Session } from './session.svelte';

	let {
		spot,
		session = sharedSession,
		favourites = sharedFavourites,
		showLoadError = true
	}: {
		spot: StudySpot;
		session?: Session;
		favourites?: Favourites;
		showLoadError?: boolean;
	} = $props();
	let prompt = $state(false);
	let loginError = $state('');
	const origin = $derived(`/spots/${spot.id}`);
	const saved = $derived(favourites.saved(spot.id));
	const action = $derived(favourites.action(spot.id));
	const eligible = $derived(
		session.status === 'signed-in' && session.account?.account_type === 'student'
	);
	const visible = $derived(
		session.status === 'signed-out' ||
			(session.status === 'signed-in' && session.account?.account_type !== 'business')
	);

	$effect(() => {
		const scope = session.scope;
		if (scope && eligible)
			untrack(() => {
				void favourites.load();
			});
		if (!scope) prompt = false;
	});

	async function login(): Promise<void> {
		loginError = '';
		try {
			await session.logIn(origin);
		} catch {
			loginError = 'Could not open login. Please try again.';
		}
	}
</script>

{#if visible}
	<div class="favourite">
		{#if session.status === 'signed-out'}
			<button type="button" aria-expanded={prompt} onclick={() => (prompt = !prompt)}>Save</button>
			{#if prompt}
				<div class="prompt" aria-label="Save this study spot">
					<p>
						Log in or sign up to save this spot. You’ll return here without saving automatically.
					</p>
					<button type="button" onclick={login}>Log in</button>
					<a href={resolve(`/signup?returnTo=${encodeURIComponent(origin)}`)}>Sign up</a>
					{#if loginError}<p role="alert">{loginError}</p>{/if}
				</div>
			{/if}
		{:else if !eligible}
			<a href={resolve(`/account?returnTo=${encodeURIComponent(origin)}`)}>Finish sign-up to save</a
			>
		{:else}
			<button
				type="button"
				aria-pressed={saved === true}
				aria-label={action?.error
					? `Retry ${action.desired ? 'saving' : 'removing'} ${spot.name}`
					: `${saved ? 'Unsave' : 'Save'} ${spot.name}`}
				disabled={saved === undefined || action?.pending}
				onclick={() => favourites.change(spot, action?.error ? action.desired : !saved)}
			>
				{#if action?.pending}{action.desired ? 'Saving…' : 'Removing…'}
				{:else if action?.error}Retry {action.desired ? 'Save' : 'Unsave'}
				{:else if saved === undefined}{favourites.status === 'error' ? 'Unavailable' : 'Loading…'}
				{:else}{saved ? 'Unsave' : 'Save'}{/if}
			</button>
			{#if action?.error}<p class="error" role="alert">{action.error}</p>{/if}
			{#if showLoadError && favourites.status === 'error'}
				<p class="error" role="alert">{favourites.error}</p>
				<button type="button" onclick={() => favourites.load({ refresh: true })}
					>Retry loading favourites</button
				>
			{/if}
		{/if}
	</div>
{/if}

<style>
	.favourite {
		position: relative;
		display: inline-flex;
		flex-wrap: wrap;
		align-items: flex-start;
		gap: 6px;
	}
	button,
	a {
		display: inline-flex;
		min-height: 44px;
		align-items: center;
		justify-content: center;
		padding: 0 14px;
		border: 1px solid var(--color-border);
		border-radius: 10px;
		color: var(--color-text);
		background: white;
		font-size: 13px;
		font-weight: 650;
		cursor: pointer;
	}
	button:hover:not(:disabled),
	a:hover {
		border-color: var(--color-text);
	}
	button[aria-pressed='true'] {
		color: var(--color-brand-hover);
		border-color: var(--color-brand-hover);
	}
	button:disabled {
		color: var(--color-muted);
		cursor: progress;
	}
	button:focus-visible,
	a:focus-visible {
		outline: 3px solid var(--color-brand-hover);
		outline-offset: 3px;
	}
	.prompt {
		flex-basis: 100%;
		padding: 12px;
		border: 1px solid var(--color-border);
		border-radius: 12px;
		background: #f7f1eb;
	}
	.prompt p {
		margin: 0 0 10px;
		font-size: 13px;
		line-height: 1.5;
	}
	.prompt a {
		margin-left: 6px;
	}
	.error {
		flex-basis: 100%;
		margin: 4px 0;
		color: var(--color-brand-hover);
		font-size: 13px;
		line-height: 1.5;
	}
</style>
