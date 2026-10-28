<script lang="ts">
	import { untrack } from 'svelte';
	import { ApiError } from './api';
	import type { AccountType, CompleteSignUp, UsernameCheck } from './contract';

	/**
	 * Student or business, and the name that goes with it.
	 *
	 * Shared by the sign-up page, before Auth0 has been to, and the account page,
	 * after, so the question looks and behaves the same in both places.
	 */
	let {
		onSubmit,
		submitLabel,
		askUsername = true,
		email = '',
		initial = null,
		error = null,
		check
	}: {
		/** Throws an `ApiError` for the form to show; anything else is a failure. */
		onSubmit: (choice: CompleteSignUp) => Promise<void>;
		submitLabel: string;
		/** False when Auth0 already holds a username for this person. */
		askUsername?: boolean;
		/** The address the account will use, once it is known. */
		email?: string;
		/** Values to start from, as when a pending sign-up was refused. */
		initial?: CompleteSignUp | null;
		/** A refusal to show from the start. */
		error?: ApiError | null;
		/** Asks the API whether a username is free; the session's, in practice. */
		check: (username: string) => Promise<UsernameCheck>;
	} = $props();

	/** Mirrors the API's rule, so most mistakes are caught before a request. */
	const USERNAME = /^[A-Za-z0-9_.]{3,30}$/;

	// Seeded once from the props: the form owns these values from then on.
	let choice = $state<AccountType>(untrack(() => initial?.account_type ?? 'student'));
	let username = $state(
		untrack(() => (initial?.account_type === 'student' ? (initial.username ?? '') : ''))
	);
	let businessName = $state(
		untrack(() => (initial?.account_type === 'business' ? initial.business_name : ''))
	);
	let submitting = $state(false);

	let formError = $state('');
	let fieldErrors = $state<Record<string, string>>(untrack(() => fieldsOf(error)));

	/** The availability answer for the username in the box, once there is one. */
	let availability = $state<UsernameCheck | null>(null);
	let checking = $state(false);

	/** Per-field messages from an API refusal, keyed by the field they are about. */
	function fieldsOf(refusal: ApiError | null): Record<string, string> {
		if (!refusal) return {};
		if (refusal.details.length === 0) return { form: refusal.message };
		// "body.business_name" -> "business_name".
		return Object.fromEntries(
			refusal.details.map((detail) => [
				(detail.field ?? 'form').replace(/^body\./, ''),
				detail.message
			])
		);
	}

	/**
	 * Ask whether the name is free once typing pauses.
	 *
	 * Tagged like the homepage's searches, so a slow answer for "gra" cannot
	 * land after the one for "grace".
	 */
	let latestCheck = 0;
	let checkTimer: ReturnType<typeof setTimeout> | undefined;

	$effect(() => {
		const name = username.trim();
		const request = ++latestCheck;
		clearTimeout(checkTimer);
		availability = null;
		checking = false;

		if (!askUsername || choice !== 'student' || !USERNAME.test(name)) return;

		checking = true;
		checkTimer = setTimeout(() => {
			check(name)
				.then((answer) => {
					if (request === latestCheck) availability = answer;
				})
				// The check is a courtesy: if it fails, submitting still decides.
				.catch(() => {})
				.finally(() => {
					if (request === latestCheck) checking = false;
				});
		}, 300);

		return () => clearTimeout(checkTimer);
	});

	function validate(): Record<string, string> {
		const problems: Record<string, string> = {};
		if (choice === 'student' && askUsername) {
			const name = username.trim();
			if (!name) problems.username = 'Choose a username.';
			else if (!USERNAME.test(name)) {
				problems.username = 'Use 3 to 30 letters, numbers, dots or underscores.';
			} else if (availability && !availability.available && availability.message) {
				problems.username = availability.message;
			}
		}
		if (choice === 'business' && !businessName.trim()) {
			problems.business_name = 'Enter your business name.';
		}
		return problems;
	}

	async function submit(event: SubmitEvent): Promise<void> {
		event.preventDefault();
		if (submitting) return;

		formError = '';
		fieldErrors = validate();
		if (Object.keys(fieldErrors).length > 0) return;

		submitting = true;
		try {
			await onSubmit(
				choice === 'business'
					? { account_type: 'business', business_name: businessName.trim() }
					: askUsername
						? { account_type: 'student', username: username.trim() }
						: { account_type: 'student' }
			);
		} catch (failure) {
			if (failure instanceof ApiError) {
				const fields = fieldsOf(failure);
				formError = fields.form ?? '';
				delete fields.form;
				fieldErrors = fields;
			} else {
				formError = 'Something went wrong. Try again.';
			}
		} finally {
			submitting = false;
		}
	}
</script>

<form class="sign-up" onsubmit={submit} novalidate>
	<fieldset>
		<legend>Account type</legend>

		<label class="option" class:selected={choice === 'student'}>
			<input type="radio" name="account_type" value="student" bind:group={choice} />
			<span>
				<span class="option-title">Student</span>
				<span class="option-text">
					Find study spots and study partners.
					{#if email}
						Uses your university email, {email}.
					{:else}
						Sign up with your university email.
					{/if}
				</span>
			</span>
		</label>

		<label class="option" class:selected={choice === 'business'}>
			<input type="radio" name="account_type" value="business" bind:group={choice} />
			<span>
				<span class="option-title">Business owner</span>
				<span class="option-text">Manage the listing for your study space.</span>
			</span>
		</label>
	</fieldset>

	{#if fieldErrors.email}
		<p class="field-error" role="alert">{fieldErrors.email}</p>
	{/if}
	{#if fieldErrors.account_type}
		<p class="field-error" role="alert">{fieldErrors.account_type}</p>
	{/if}

	{#if choice === 'student' && askUsername}
		<label class="field">
			<span class="label">Username</span>
			<input
				type="text"
				name="username"
				autocomplete="username"
				autocapitalize="none"
				spellcheck="false"
				minlength="3"
				maxlength="30"
				required
				bind:value={username}
				aria-describedby="username-hint"
				aria-invalid={fieldErrors.username || availability?.available === false
					? 'true'
					: undefined}
			/>
		</label>
		<!-- Polite, so the answer is read out without interrupting typing. -->
		<p class="hint-text" id="username-hint" aria-live="polite">
			{#if checking}
				Checking…
			{:else if availability?.available}
				<span class="ok">✓ {availability.username} is available</span>
			{:else if availability && !fieldErrors.username}
				<span class="bad">{availability.message}</span>
			{:else}
				What other students see. Letters, numbers, dots and underscores.
			{/if}
		</p>
		{#if fieldErrors.username}
			<p class="field-error" role="alert">{fieldErrors.username}</p>
		{/if}
	{/if}

	{#if choice === 'business'}
		<label class="field">
			<span class="label">Business name</span>
			<input
				type="text"
				name="business_name"
				autocomplete="organization"
				maxlength="200"
				required
				bind:value={businessName}
				aria-invalid={fieldErrors.business_name ? 'true' : undefined}
			/>
		</label>
		{#if fieldErrors.business_name}
			<p class="field-error" role="alert">{fieldErrors.business_name}</p>
		{/if}
	{/if}

	{#if formError}
		<p class="field-error" role="alert">{formError}</p>
	{/if}

	<button class="primary" type="submit" disabled={submitting}>
		{submitting ? 'Saving…' : submitLabel}
	</button>
</form>

<style>
	.sign-up {
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

	fieldset {
		display: flex;
		flex-direction: column;
		gap: 10px;
		margin: 0;
		padding: 0;
		border: 0;
	}

	legend {
		margin-bottom: 10px;
		padding: 0;
		font-size: 13px;
		font-weight: 700;
	}

	.option {
		display: flex;
		align-items: flex-start;
		gap: 12px;
		padding: 14px 16px;
		border: 1px solid var(--color-border);
		border-radius: 16px;
		cursor: pointer;
		transition:
			border-color 150ms ease,
			background-color 150ms ease;
	}

	.option:hover {
		background: #fbf8f5;
	}

	.option.selected {
		border-color: #222;
		background: #fbf8f5;
	}

	.option input {
		margin: 3px 0 0;
		accent-color: var(--color-brand-hover);
	}

	.option-title {
		display: block;
		font-size: 15px;
		font-weight: 700;
	}

	.option-text {
		display: block;
		margin-top: 2px;
		color: var(--color-muted);
		font-size: 14px;
		line-height: 1.45;
		overflow-wrap: anywhere;
	}

	.field {
		display: flex;
		flex-direction: column;
		gap: 6px;
	}

	.label {
		font-size: 13px;
		font-weight: 700;
	}

	.field input {
		min-height: 48px;
		padding: 0 16px;
		border: 1px solid var(--color-border);
		border-radius: 14px;
		color: var(--color-text);
		background: #fff;
	}

	.field input:focus-visible {
		border-color: #222;
		outline: 3px solid rgb(255 56 92 / 25%);
		outline-offset: 0;
	}

	.field input[aria-invalid='true'] {
		border-color: var(--color-brand-hover);
	}

	.hint-text {
		margin: -8px 0 0;
		color: var(--color-muted);
		font-size: 13px;
	}

	.ok {
		color: #1f6b3a;
		font-weight: 600;
	}

	.bad,
	.field-error {
		color: var(--color-brand-hover);
		font-weight: 600;
	}

	.field-error {
		margin: 0;
		font-size: 14px;
	}

	.primary {
		display: inline-flex;
		min-height: 48px;
		align-items: center;
		justify-content: center;
		padding: 0 22px;
		border: 0;
		border-radius: 999px;
		color: #fff;
		font-size: 15px;
		font-weight: 650;
		background: var(--color-brand-hover);
		cursor: pointer;
		transition: background-color 150ms ease;
	}

	.primary:hover {
		background: #b50935;
	}

	.primary:disabled {
		cursor: progress;
		opacity: 0.7;
	}

	.primary:focus-visible {
		outline: 3px solid var(--color-brand-hover);
		outline-offset: 3px;
	}
</style>
