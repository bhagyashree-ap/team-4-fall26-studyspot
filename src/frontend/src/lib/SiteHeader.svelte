<script lang="ts">
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { displayName } from './accounts';
	import { session as shared, type Session } from './session.svelte';

	type Props = {
		/** Replaceable so a test can render the header in any state. */
		session?: Session;
		/**
		 * What the Map tab should do on a page that is already showing
		 * results. Given, the tab switches them to the map; left out, it is a
		 * link to the homepage's map view.
		 */
		onMap?: () => void;
	};

	let { session = shared, onMap }: Props = $props();
	const menuId = $props.id();
	let mobileMenu: HTMLDivElement;

	/** Back to this page after logging in, rather than to the homepage. */
	const here = $derived(page.url.pathname + page.url.search);
</script>

{#snippet destinations()}
	<a class="nav-link" href={resolve('/')}>Explore</a>
	<a class="nav-link" data-sveltekit-reload href={resolve('/communities')}>Communities</a>
	{#if onMap}
		<!--
				A button, because from here it goes nowhere: the results are on
				this page already and navigating would lose the search.
			-->
		<button
			class="nav-link"
			type="button"
			onclick={() => {
				mobileMenu?.hidePopover();
				onMap?.();
			}}>Map</button
		>
	{:else}
		<!--
				From anywhere else it is a real link home, and says in the URL
				what it is going there for -- which also makes the map view
				something that can be sent to someone.
			-->
		<a class="nav-link" href="{resolve('/')}?view=map">Map</a>
	{/if}
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
{/snippet}

<header>
	<a class="brand" href={resolve('/')} aria-label="StudySpot home">
		<svg viewBox="0 0 32 32" aria-hidden="true">
			<path d="M7 7.5h18v17H7z"></path>
			<path d="M11 12h10M11 16h10M11 20h6"></path>
		</svg>
		<span>StudySpot</span>
	</a>
	<nav aria-label="Main navigation">
		<div class="wide-links">{@render destinations()}</div>
		<button class="nav-link menu-trigger" popovertarget={menuId} aria-label="Site navigation"
			>Menu <span aria-hidden="true">▾</span></button
		>
		<div id={menuId} bind:this={mobileMenu} popover="auto" class="compact-links">
			{@render destinations()}
		</div>
	</nav>
</header>

<style>
	header {
		display: flex;
		width: 100%;
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

	nav,
	.wide-links {
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

	.menu-trigger,
	.compact-links {
		display: none;
	}
	.brand:focus-visible {
		outline: 3px solid var(--color-brand-hover);
		outline-offset: 2px;
	}
	@media (max-width: 740px) {
		header {
			height: 56px;
			gap: 8px;
		}
		.wide-links {
			display: none;
		}
		.menu-trigger {
			display: inline-flex;
			gap: 6px;
		}
		.compact-links:popover-open {
			position: fixed;
			inset: 52px 10px auto auto;
			margin: 0;
			display: grid;
			gap: 4px;
			width: min(15rem, calc(100vw - 20px));
			max-height: calc(100dvh - 60px);
			overflow: auto;
			background: var(--site-menu-bg, white);
			padding: 8px;
			border: 1px solid var(--site-menu-border, #ddd);
			border-radius: 12px;
			box-shadow: 0 8px 22px #0002;
		}
		.compact-links :is(.nav-link, .sign-in) {
			margin: 0;
			max-width: 100%;
			justify-content: flex-start;
		}
	}
</style>
