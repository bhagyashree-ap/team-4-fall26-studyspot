<script lang="ts">
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { displayName } from './accounts';
	import { session as shared, type Session } from './session.svelte';

	/** Replaceable so a test can render the header in any state. */
	let { session = shared }: { session?: Session } = $props();

	/** Back to this page after logging in, rather than to the homepage. */
	const here = $derived(page.url.pathname + page.url.search);
</script>

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

		<!--
			Nothing until the session is known, so a prerendered "Log in" never
			flashes at someone who is already logged in. With accounts switched
			off there is nothing to offer at all.
		-->
		{#if session.status === 'signed-in' && session.account}
			<a class="sign-in account" href={resolve('/account')}>
				<span class="avatar" aria-hidden="true">
					{displayName(session.account).charAt(0).toUpperCase()}
				</span>
				<span class="name">{displayName(session.account)}</span>
			</a>
		{:else if session.status === 'signed-out'}
			<button class="nav-link" type="button" onclick={() => session.logIn(here)}>Log in</button>
			<a class="sign-in" href={resolve('/signup')}>Sign up</a>
		{/if}
	</nav>
</header>

<style>
	header {
		display: flex;
		width: min(1180px, 100%);
		height: 76px;
		align-items: center;
		justify-content: space-between;
		margin: 0 auto;
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
		color: var(--color-text);
		font-size: 14px;
		font-weight: 650;
		line-height: 1.2;
		background: #fff;
		cursor: pointer;
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

	.account {
		gap: 8px;
		max-width: 220px;
		padding-left: 6px;
	}

	.avatar {
		display: inline-grid;
		width: 30px;
		height: 30px;
		flex: none;
		place-items: center;
		border-radius: 50%;
		color: #fff;
		font-size: 13px;
		font-weight: 750;
		background: var(--color-brand-hover);
	}

	.name {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.nav-link:focus-visible,
	.sign-in:focus-visible {
		outline: 3px solid var(--color-brand-hover);
		outline-offset: 3px;
	}

	@media (max-width: 560px) {
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

		.avatar {
			width: 26px;
			height: 26px;
			font-size: 12px;
		}
	}
</style>
