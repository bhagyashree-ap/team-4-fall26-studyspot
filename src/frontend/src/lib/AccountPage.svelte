<script lang="ts">
	import { resolve } from '$app/paths';
	import SiteHeader from './SiteHeader.svelte';
	import SignUpForm from './SignUpForm.svelte';
	import type { CompleteSignUp } from './contract';
	import { session as shared, type Session } from './session.svelte';

	/** Replaceable so a test can render the page in any state. */
	let { session = shared }: { session?: Session } = $props();

	const account = $derived(session.account);
	let refreshing = $state(false);

	const joined = $derived(
		account
			? new Date(account.created_at).toLocaleDateString('en-US', {
					month: 'long',
					year: 'numeric'
				})
			: ''
	);

	/** What the sign-up page chose, said back while the email is unverified. */
	const pendingSummary = $derived.by(() => {
		const pending = session.pending;
		if (!pending) return '';
		if (pending.account_type === 'business')
			return `a business account for ${pending.business_name}`;
		return pending.username ? `a student account as ${pending.username}` : 'a student account';
	});

	async function finish(choice: CompleteSignUp): Promise<void> {
		await session.completeSignUp(choice);
	}

	async function checkVerified(): Promise<void> {
		refreshing = true;
		await session.refresh();
		refreshing = false;
	}
</script>

<div class="page">
	<SiteHeader {session} />

	<main aria-live="polite">
		{#if session.status === 'loading'}
			<p class="status">Loading your account…</p>
		{:else if session.status === 'disabled'}
			<p class="status">Accounts are not switched on for this site yet.</p>
		{:else if session.status === 'error'}
			<p class="status error" role="alert">{session.error}</p>
		{:else if session.status === 'signed-out'}
			<section class="panel" aria-labelledby="account-title">
				<p class="eyebrow">Accounts</p>
				<h1 id="account-title">Join StudySpot.</h1>
				<p class="lede">
					Students sign up with their university email. Business owners sign up to manage the
					listing for their space.
				</p>
				<div class="actions">
					<a class="primary" href={resolve('/signup')}>Sign up</a>
					<button class="secondary" type="button" onclick={() => session.logIn('/account')}>
						Log in
					</button>
				</div>
				<p class="hint">Forgot your password? Choose “Log in”, then “Forgot password?”.</p>
			</section>
		{:else if account && !account.email_verified}
			<section class="panel" aria-labelledby="account-title">
				<p class="eyebrow">One more step</p>
				<h1 id="account-title">Verify your email.</h1>
				<p class="lede">
					We sent a link to <strong>{account.email}</strong>. Open it, then come back here.
					{#if pendingSummary}
						We’ll finish setting up {pendingSummary} as soon as it’s verified.
					{/if}
				</p>
				<div class="actions">
					<button class="primary" type="button" disabled={refreshing} onclick={checkVerified}>
						{refreshing ? 'Checking…' : 'I’ve verified it'}
					</button>
					<button class="secondary" type="button" onclick={() => session.logOut()}>Log out</button>
				</div>
			</section>
		{:else if account && account.account_type === null}
			<section class="panel" aria-labelledby="account-title">
				<p class="eyebrow">One more step</p>
				<h1 id="account-title">Who is this account for?</h1>

				<SignUpForm
					onSubmit={finish}
					submitLabel="Finish sign-up"
					askUsername={!account.username}
					email={account.email}
					initial={session.pending}
					error={session.pendingError}
					check={(name) => session.checkUsername(name)}
				/>
			</section>
		{:else if account}
			<section class="panel" aria-labelledby="account-title">
				<p class="eyebrow">
					{account.account_type === 'business' ? 'Business' : 'Student'} account
				</p>
				<h1 id="account-title">
					{account.account_type === 'business' ? account.business_name : account.username}
				</h1>

				<dl class="card">
					{#if account.account_type === 'student'}
						<dt>Username</dt>
						<dd>{account.username}</dd>
					{:else}
						<dt>Business name</dt>
						<dd>{account.business_name}</dd>
					{/if}
					<dt>Email</dt>
					<dd>{account.email} <span class="badge">Verified</span></dd>
					<dt>Member since</dt>
					<dd>{joined}</dd>
				</dl>

				<div class="actions">
					<a class="secondary" href={resolve('/')}>Find a study spot</a>
					<button class="secondary" type="button" onclick={() => session.logOut()}>Log out</button>
				</div>
			</section>
		{/if}
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
		overflow-wrap: anywhere;
	}

	.lede {
		max-width: 520px;
		margin: 0;
		color: var(--color-muted);
		font-size: 17px;
		line-height: 1.6;
	}

	.lede strong {
		color: var(--color-text);
	}

	.hint {
		margin: 0;
		color: var(--color-muted);
		font-size: 13px;
	}

	.actions {
		display: flex;
		flex-wrap: wrap;
		justify-content: center;
		gap: 10px;
	}

	.primary,
	.secondary {
		display: inline-flex;
		min-height: 48px;
		align-items: center;
		justify-content: center;
		padding: 0 22px;
		border-radius: 999px;
		font-size: 15px;
		font-weight: 650;
		cursor: pointer;
		transition: background-color 150ms ease;
	}

	.primary {
		border: 0;
		color: #fff;
		background: var(--color-brand-hover);
	}

	.primary:hover {
		background: #b50935;
	}

	.primary:disabled {
		cursor: progress;
		opacity: 0.7;
	}

	.secondary {
		border: 1px solid var(--color-border);
		color: var(--color-text);
		background: #fff;
	}

	.secondary:hover {
		background: #fbf8f5;
	}

	.primary:focus-visible,
	.secondary:focus-visible {
		outline: 3px solid var(--color-brand-hover);
		outline-offset: 3px;
	}

	.card {
		display: flex;
		width: min(560px, 100%);
		flex-direction: column;
		gap: 14px;
		margin: 0;
		padding: 20px;
		border: 1px solid var(--color-border);
		border-radius: 24px;
		background: #fff;
		box-shadow: 0 16px 44px rgb(34 34 34 / 9%);
		text-align: left;
	}

	dl.card {
		display: grid;
		grid-template-columns: max-content 1fr;
		gap: 12px 24px;
	}

	dt {
		color: var(--color-muted);
		font-size: 14px;
	}

	dd {
		margin: 0;
		font-size: 15px;
		font-weight: 600;
		overflow-wrap: anywhere;
	}

	.badge {
		display: inline-block;
		margin-left: 6px;
		padding: 2px 8px;
		border-radius: 999px;
		color: #1f6b3a;
		font-size: 12px;
		font-weight: 700;
		background: #e6f4ea;
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

	@media (max-width: 560px) {
		.page {
			padding: 0 12px 15px;
		}

		.panel {
			padding: 40px 16px 48px;
			border-radius: 24px;
		}

		dl.card {
			grid-template-columns: 1fr;
			gap: 2px;
		}

		dd + dt {
			margin-top: 10px;
		}
	}
</style>
