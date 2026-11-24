<script lang="ts">
	import type { Review } from './contract';

	let {
		review,
		busy,
		error,
		onsave,
		ondelete
	}: {
		review: Review;
		busy: boolean;
		error: string;
		onsave: (body: string) => Promise<boolean>;
		ondelete: () => Promise<boolean>;
	} = $props();
	const id = $props.id();
	let mode = $state<'closed' | 'editing' | 'deleting'>('closed');
	let body = $state('');

	function edit(): void {
		body = review.reply?.body ?? '';
		mode = 'editing';
	}

	async function submit(event: SubmitEvent): Promise<void> {
		event.preventDefault();
		if (!busy && body.trim() && (await onsave(body))) mode = 'closed';
	}

	async function remove(): Promise<void> {
		if (!busy && (await ondelete())) mode = 'closed';
	}
</script>

<div class="reviews-reply-editor">
	{#if error}<p class="reviews-error" role="alert">{error}</p>{/if}
	{#if mode === 'editing'}
		<form
			class="reviews-form"
			aria-label={review.reply ? 'Edit owner reply' : 'Reply to review'}
			onsubmit={submit}
		>
			<div class="reviews-field">
				<label for={`${id}-reply`}>Public reply</label>
				<p class="reviews-note" id={`${id}-help`}>Public replies can be up to 2,000 characters.</p>
				<textarea
					id={`${id}-reply`}
					rows="3"
					maxlength="2000"
					aria-describedby={`${id}-help`}
					required
					bind:value={body}
					disabled={busy}></textarea>
			</div>
			<div class="reviews-actions">
				<button type="submit" class="reviews-primary" disabled={busy || !body.trim()}
					>{review.reply ? 'Save reply' : 'Post reply'}</button
				>
				<button type="button" disabled={busy} onclick={() => (mode = 'closed')}>Cancel</button>
			</div>
		</form>
	{:else if mode === 'deleting'}
		<p class="reviews-confirm">Delete this public reply? This cannot be undone.</p>
		<div class="reviews-actions">
			<button type="button" class="reviews-danger" disabled={busy} onclick={remove}
				>Confirm delete reply</button
			>
			<button type="button" disabled={busy} onclick={() => (mode = 'closed')}>Cancel</button>
		</div>
	{:else}
		<div class="reviews-actions">
			<button type="button" disabled={busy} onclick={edit}
				>{review.reply ? 'Edit reply' : 'Reply'}</button
			>
			{#if review.reply}
				<button type="button" disabled={busy} onclick={() => (mode = 'deleting')}
					>Delete reply</button
				>
			{/if}
		</div>
	{/if}
</div>
