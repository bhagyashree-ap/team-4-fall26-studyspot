<script lang="ts">
	import type { Snippet } from 'svelte';
	import type { Review } from './contract';
	import { reviewScoreFields } from './review-fields';

	let { review, children }: { review: Review; children?: Snippet } = $props();

	const scores = $derived(
		reviewScoreFields.flatMap(([field, label]) =>
			review[field] === null ? [] : [`${label} ${review[field]}/5`]
		)
	);

	function postedOn(timestamp: string): string {
		return new Date(timestamp).toLocaleDateString('en-US', {
			month: 'short',
			day: 'numeric',
			year: 'numeric'
		});
	}
</script>

<article class="reviews-card" aria-label={`Review by ${review.author.username ?? 'a student'}`}>
	<p class="reviews-byline">
		<span class="reviews-author">{review.author.username ?? 'A student'}</span>
		· <time datetime={review.created_at}>{postedOn(review.created_at)}</time>
		· <span class="reviews-rating">Overall {review.rating}/5</span>
	</p>
	{#if scores.length > 0}<p class="reviews-scores">{scores.join(' · ')}</p>{/if}
	{#if review.body}<p class="reviews-body">{review.body}</p>{/if}
	{#if review.reply}
		<div class="reviews-owner-reply">
			<p class="reviews-reply-title">Reply from the owner</p>
			<p class="reviews-body">{review.reply.body}</p>
		</div>
	{/if}
	{@render children?.()}
</article>
