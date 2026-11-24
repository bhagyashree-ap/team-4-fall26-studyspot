<script lang="ts">
	import { untrack } from 'svelte';
	import { listReviews, type Fetcher } from './api';
	import type { Review } from './contract';

	let { spotId, fetcher }: { spotId: string; fetcher?: Fetcher } = $props();

	type Status = { kind: 'loading' } | { kind: 'ready'; reviews: Review[] } | { kind: 'error' };

	let status = $state<Status>({ kind: 'loading' });

	/**
	 * Following a nearby link swaps `spotId` without remounting, so a slow reply
	 * for the previous spot can land after the current one's. Only the latest
	 * request may write.
	 */
	let latest = 0;

	function load(id: string): void {
		const request = ++latest;
		status = { kind: 'loading' };
		listReviews(id, { fetcher })
			.then((page) => {
				if (request === latest) status = { kind: 'ready', reviews: page.items };
			})
			.catch(() => {
				if (request === latest) status = { kind: 'error' };
			});
	}

	// Effects run only in the browser, never while prerendering, so reviews are
	// always current rather than frozen at build time.
	$effect(() => {
		const id = spotId;
		untrack(() => load(id));
	});

	/** `noise` reads as "Quiet": on every score 5 is best, so 5 is very quiet. */
	const SCORES = [
		['noise', 'Quiet'],
		['wifi', 'Wi-Fi'],
		['seating', 'Seating'],
		['outlets', 'Outlets']
	] as const;

	function scores(review: Review): { label: string; value: number }[] {
		return SCORES.flatMap(([field, label]) => {
			const value = review[field];
			return value === null ? [] : [{ label, value }];
		});
	}

	function postedOn(timestamp: string): string {
		return new Date(timestamp).toLocaleDateString('en-US', {
			month: 'short',
			day: 'numeric',
			year: 'numeric'
		});
	}
</script>

<section aria-labelledby="reviews-title">
	<h2 id="reviews-title">Reviews <span class="scale">5 is best</span></h2>

	{#if status.kind === 'loading'}
		<p class="note" role="status">Loading reviews…</p>
	{:else if status.kind === 'error'}
		<p class="error" role="alert">Could not load reviews.</p>
		<button type="button" onclick={() => load(spotId)}>Try again</button>
	{:else if status.reviews.length === 0}
		<p class="note">No reviews yet.</p>
	{:else}
		<ul>
			{#each status.reviews as review (review.id)}
				<li>
					<p class="byline">
						<span class="author">{review.author.username ?? 'A student'}</span>
						· <time datetime={review.created_at}>{postedOn(review.created_at)}</time>
						· <span class="rating">Overall {review.rating}/5</span>
					</p>
					{#if scores(review).length > 0}
						<p class="scores">
							{scores(review)
								.map(({ label, value }) => `${label} ${value}/5`)
								.join(' · ')}
						</p>
					{/if}
					{#if review.body}
						<p class="body">{review.body}</p>
					{/if}
				</li>
			{/each}
		</ul>
	{/if}
</section>

<style>
	section {
		margin-top: 40px;
	}

	h2 {
		margin: 0 0 16px;
		font-size: 17px;
		font-weight: 700;
		letter-spacing: -0.02em;
	}

	.scale {
		margin-left: 6px;
		color: var(--color-muted);
		font-size: 13px;
		font-weight: 500;
		letter-spacing: 0;
	}

	ul {
		display: grid;
		gap: 10px;
		margin: 0;
		padding: 0;
		list-style: none;
	}

	li {
		padding: 16px 20px;
		border: 1px solid var(--color-border);
		border-radius: 14px;
		background: white;
	}

	p {
		margin: 0;
	}

	.byline {
		color: var(--color-muted);
		font-size: 13px;
	}

	.author,
	.rating {
		color: var(--color-text);
		font-weight: 650;
	}

	.scores {
		margin-top: 6px;
		font-size: 13px;
	}

	.body {
		margin-top: 10px;
		font-size: 15px;
		line-height: 1.55;
		/* Keeps the line breaks the author typed. */
		white-space: pre-line;
	}

	.note {
		color: var(--color-muted);
		font-size: 14px;
	}

	.error {
		color: var(--color-brand-hover);
		font-size: 14px;
	}

	button {
		display: inline-flex;
		min-height: 44px;
		align-items: center;
		margin-top: 10px;
		padding: 0 14px;
		border: 1px solid var(--color-border);
		border-radius: 10px;
		color: var(--color-text);
		background: white;
		font-size: 13px;
		font-weight: 650;
		cursor: pointer;
	}

	button:hover {
		border-color: var(--color-text);
	}

	button:focus-visible {
		outline: 3px solid var(--color-brand-hover);
		outline-offset: 3px;
	}
</style>
