<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import SiteHeader from '$lib/SiteHeader.svelte';
	import { session } from '$lib/session.svelte';

	// Auth0 sends the browser here with a one-time code in the query string. It
	// is exchanged for tokens, and the page is replaced in history so the back
	// button does not try to spend the same code twice.
	onMount(async () => {
		const next = await session.finishLogIn();
		if (session.status !== 'error') await goto(resolve(next as '/'), { replaceState: true });
	});
</script>

<svelte:head>
	<title>Logging in — StudySpot</title>
	<meta name="robots" content="noindex" />
</svelte:head>

<div class="page">
	<SiteHeader />
	<main aria-live="polite">
		{#if session.status === 'error'}
			<p class="panel error" role="alert">{session.error}</p>
			<p class="back">
				<!--
				A full load rather than client-side navigation: the session has
				already settled on this error, and only a fresh start retries.
			-->
				<a href={resolve('/account')} data-sveltekit-reload>Try again</a>
			</p>
		{:else}
			<p class="panel">Logging you in…</p>
		{/if}
	</main>
</div>

<style>
	.page {
		min-height: 100vh;
		padding: 0 24px 24px;
	}

	main {
		width: min(560px, 100%);
		margin: 48px auto 0;
	}

	.panel {
		margin: 0;
		padding: 24px;
		border: 1px solid var(--color-border);
		border-radius: 20px;
		color: var(--color-muted);
		background: #fff;
		font-size: 15px;
		text-align: center;
	}

	.panel.error {
		color: var(--color-brand-hover);
		font-weight: 600;
	}

	.back {
		margin: 16px 0 0;
		text-align: center;
	}

	.back a {
		font-weight: 650;
		text-decoration: underline;
	}

	@media (max-width: 560px) {
		.page {
			padding: 0 12px 15px;
		}
	}
</style>
