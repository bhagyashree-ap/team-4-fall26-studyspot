<script lang="ts">
	import { untrack } from 'svelte';
	import type { ReviewDraft } from './contract';
	import { reviewScoreFields } from './review-fields';

	let {
		initial,
		saving,
		error,
		onsubmit,
		oncancel
	}: {
		initial: ReviewDraft | null;
		saving: boolean;
		error: string;
		onsubmit: (draft: ReviewDraft) => void;
		oncancel: () => void;
	} = $props();
	const id = $props.id();
	const original = untrack(() => initial);
	let rating = $state<number | ''>(original?.rating ?? '');
	let optional = $state({
		noise: original?.noise ?? null,
		wifi: original?.wifi ?? null,
		seating: original?.seating ?? null,
		outlets: original?.outlets ?? null
	});
	let body = $state(original?.body ?? '');

	function submit(event: SubmitEvent): void {
		event.preventDefault();
		if (saving || rating === '') return;
		onsubmit({ rating, ...optional, body });
	}
</script>

<form
	class="reviews-form"
	aria-label={initial ? 'Edit your review' : 'Write your review'}
	onsubmit={submit}
>
	<p class="reviews-note" id={`${id}-help`}>
		Overall rating is required. Other ratings and review text are optional. 5 is best. Review text
		can be up to 2,000 characters.
	</p>
	<fieldset disabled={saving} aria-describedby={`${id}-help`}>
		<legend class="reviews-sr-only">Rate this study spot</legend>
		<div class="reviews-rating-fields">
			<div class="reviews-field">
				<label for={`${id}-overall`}>Overall rating</label>
				<select id={`${id}-overall`} bind:value={rating} required>
					<option value="" disabled>Choose a rating</option>
					{#each [1, 2, 3, 4, 5] as score (score)}<option value={score}>{score}</option>{/each}
				</select>
			</div>
			{#each reviewScoreFields as [field, label] (field)}
				<div class="reviews-field">
					<label for={`${id}-${field}`}>{label}</label>
					<select id={`${id}-${field}`} bind:value={optional[field]}>
						<option value={null}>Not rated</option>
						{#each [1, 2, 3, 4, 5] as score (score)}<option value={score}>{score}</option>{/each}
					</select>
				</div>
			{/each}
		</div>
		<div class="reviews-field">
			<label for={`${id}-body`}>Review text</label>
			<textarea id={`${id}-body`} rows="4" maxlength="2000" bind:value={body}></textarea>
		</div>
		{#if error}<p class="reviews-error" role="alert">{error}</p>{/if}
		<div class="reviews-actions">
			<button type="submit" class="reviews-primary"
				>{initial ? 'Save review' : 'Post review'}</button
			>
			<button type="button" onclick={oncancel}>Cancel</button>
		</div>
	</fieldset>
	{#if saving}<p class="reviews-note" role="status">Saving review…</p>{/if}
</form>
