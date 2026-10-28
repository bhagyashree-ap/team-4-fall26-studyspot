<script lang="ts">
	import { resolve } from '$app/paths';
	import SiteHeader from './SiteHeader.svelte';
	import SignUpForm from './SignUpForm.svelte';
	import type { CompleteSignUp } from './contract';
	import { session as shared, type Session } from './session.svelte';

	/** Replaceable so a test can render the page in any state. */
	let { session = shared }: { session?: Session } = $props();

	/**
	 * StudySpot asks its own questions first, then hands over to Auth0 for the
	 * email and password, which never pass through this page. The answers wait
	 * in the session and are applied when the browser comes back verified.
	 */
	async function next(choice: CompleteSignUp): Promise<void> {
		await session.signUp(choice);
	}
</script>

<div class="page">
	<SiteHeader {session} />

	<main aria-live="polite">
		<section class="panel" aria-labelledby="sign-up-title">
			{#if session.status === 'disabled'}
				<p class="eyebrow">Accounts</p>
				<h1 id="sign-up-title">Sign-up is not open yet.</h1>
				<p class="lede">Accounts are not switched on for this site.</p>
			{:else if session.status === 'signed-in'}
				<p class="eyebrow">Accounts</p>
				<h1 id="sign-up-title">You’re already signed in.</h1>
				<div class="actions">
					<a class="primary" href={resolve('/account')}>Go to your account</a>
				</div>
			{:else}
				<p class="eyebrow">Create your account</p>
				<h1 id="sign-up-title">Join StudySpot.</h1>
				<p class="lede">
					Tell us who you are. Next, you’ll set your email and password on our secure sign-in page.
				</p>

				<SignUpForm
					onSubmit={next}
					submitLabel="Continue"
					initial={session.pending}
					check={(name) => session.checkUsername(name)}
				/>

				<p class="hint">
					Already have an account?
					<button class="link" type="button" onclick={() => session.logIn('/account')}>
						Log in
					</button>
				</p>
			{/if}
		</section>
	</main>
</div>

<style>
	.page {
		min-height: 100vh;
		padding: 0 24px 24px;
	}

	main {
		width: min(1180px, 100%);
		margin: 0 auto;
	}

	.panel {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 20px;
		padding: 64px 48px 72px;
		border-radius: 28px;
		background: #f7f1eb;
		text-align: center;
	}

	.eyebrow {
		margin: 0;
		color: var(--color-brand-hover);
		font-size: 12px;
		font-weight: 700;
		letter-spacing: 0.1em;
		text-transform: uppercase;
	}

	h1 {
		margin: 0;
		font-size: clamp(2.2rem, 5vw, 3.5rem);
		font-weight: 750;
		letter-spacing: -0.06em;
		line-height: 1;
	}

	.lede {
		max-width: 520px;
		margin: 0;
		color: var(--color-muted);
		font-size: 17px;
		line-height: 1.6;
	}

	.actions {
		display: flex;
		justify-content: center;
	}

	.primary {
		display: inline-flex;
		min-height: 48px;
		align-items: center;
		padding: 0 22px;
		border-radius: 999px;
		color: #fff;
		font-size: 15px;
		font-weight: 650;
		background: var(--color-brand-hover);
	}

	.primary:hover {
		background: #b50935;
	}

	.hint {
		margin: 0;
		color: var(--color-muted);
		font-size: 14px;
	}

	.link {
		padding: 0;
		border: 0;
		color: var(--color-text);
		font-weight: 650;
		text-decoration: underline;
		background: none;
		cursor: pointer;
	}

	@media (max-width: 560px) {
		.page {
			padding: 0 12px 15px;
		}

		.panel {
			padding: 40px 16px 48px;
			border-radius: 24px;
		}
	}
</style>
