<script lang="ts">
	import { onDestroy, untrack } from 'svelte';
	import { resolve } from '$app/paths';
	import { ApiError, listReviews, type Fetcher } from './api';
	import type {
		AccountType,
		Review,
		ReviewDraft,
		ReviewPage,
		ReviewReply,
		ReviewViewer
	} from './contract';
	import ReviewCard from './ReviewCard.svelte';
	import ReviewForm from './ReviewForm.svelte';
	import ReviewReplyEditor from './ReviewReplyEditor.svelte';
	import {
		createReview,
		deleteReview,
		deleteReviewReply,
		getReviewViewer,
		putReviewReply,
		updateReview
	} from './reviews';
	import { session as sharedSession, type Session, type SessionScope } from './session.svelte';
	import { spotPath } from './spot';
	import './reviews.css';

	let {
		spotId,
		fetcher,
		session = sharedSession
	}: { spotId: string; fetcher?: Fetcher; session?: Session } = $props();
	const id = $props.id();

	type PublicState =
		| { kind: 'loading'; spot: string }
		| { kind: 'error'; spot: string }
		| { kind: 'ready'; spot: string; page: ReviewPage; more: 'idle' | 'loading' | 'error' };
	type PrivateContext = {
		spot: string;
		session: Session;
		scope: SessionScope | null;
		fetcher?: Fetcher;
		accountType: AccountType | null | undefined;
	};
	type ViewerState =
		| { kind: 'loading' }
		| { kind: 'error'; message: string }
		| { kind: 'ready'; value: ReviewViewer };
	type Mutation = { kind: 'review' } | { kind: 'reply'; reviewId: number };
	type MutationError =
		{ kind: 'review'; message: string } | { kind: 'reply'; reviewId: number; message: string };

	let publicState = $state<PublicState>({ kind: 'loading', spot: '' });
	let context = $state.raw<PrivateContext | null>(null);
	let viewer = $state<ViewerState>({ kind: 'loading' });
	let editor = $state<'closed' | 'write' | 'edit' | 'delete'>('closed');
	let mutation = $state<Mutation | null>(null);
	let mutationError = $state<MutationError | null>(null);
	let notice = $state('');
	let publicRequest = 0;
	let viewerRequest = 0;
	let alive = true;
	let anchoredSpot: string | null = null;

	const publicPage = $derived(
		publicState.kind === 'ready' && publicState.spot === spotId ? publicState.page : null
	);
	// Optional-chained rather than read straight through: the API and the
	// frontend are published as separate steps, so an API that predates the
	// summary should leave this reading "No ratings yet" instead of throwing and
	// taking the whole section down with it.
	const average = $derived(publicPage?.summary?.average_rating ?? null);
	const privateVisible = $derived(
		context !== null &&
			context.spot === spotId &&
			context.session === session &&
			context.accountType === session.account?.account_type &&
			session.status === 'signed-in' &&
			context.scope !== null &&
			context.scope.subject === session.subject &&
			context.scope.generation === session.generation
	);
	const access = $derived(privateVisible && viewer.kind === 'ready' ? viewer.value : null);
	const ownReview = $derived(access?.kind === 'student' ? access.own_review : null);
	const publicReviews = $derived(
		publicPage?.items.filter((review) => review.id !== ownReview?.id) ?? []
	);
	const returnTo = $derived(`${spotPath(spotId)}#reviews`);

	function current(owner: PrivateContext): boolean {
		return (
			alive &&
			context === owner &&
			spotId === owner.spot &&
			session === owner.session &&
			owner.accountType === owner.session.account?.account_type &&
			owner.scope !== null &&
			owner.session.isCurrent(owner.scope)
		);
	}

	function publicCurrent(spot: string, request: number): boolean {
		return alive && spot === spotId && request === publicRequest;
	}

	async function load(spot: string, more = false, network = fetcher): Promise<void> {
		const previous = more && publicState.kind === 'ready' ? publicState.page : null;
		const request = ++publicRequest;
		if (previous) publicState = { kind: 'ready', spot, page: previous, more: 'loading' };
		else publicState = { kind: 'loading', spot };
		try {
			const page = await listReviews(spot, {
				offset: previous ? previous.pagination.offset + previous.pagination.count : 0,
				fetcher: network
			});
			if (!publicCurrent(spot, request)) return;
			publicState = {
				kind: 'ready',
				spot,
				page: {
					...page,
					items: previous
						? [
								...new Map(
									[...previous.items, ...page.items].map((item) => [item.id, item])
								).values()
							]
						: page.items
				},
				more: 'idle'
			};
		} catch {
			if (!publicCurrent(spot, request)) return;
			publicState = previous
				? { kind: 'ready', spot, page: previous, more: 'error' }
				: { kind: 'error', spot };
		}
	}

	async function refreshSummary(owner: PrivateContext): Promise<void> {
		if (!current(owner)) return;
		const spot = owner.spot;
		const request = ++publicRequest;
		try {
			const page = await listReviews(spot, { fetcher });
			if (!current(owner) || !publicCurrent(spot, request) || publicState.kind !== 'ready') return;
			publicState = {
				...publicState,
				page: {
					...publicState.page,
					summary: page.summary,
					pagination: { ...publicState.page.pagination, total: page.pagination.total }
				}
			};
		} catch {
			if (current(owner) && publicCurrent(spot, request))
				notice = 'Review saved. Refresh to update the overall rating.';
		}
	}

	function message(cause: unknown, fallback: string): string {
		return cause instanceof ApiError ? cause.message : fallback;
	}

	function rejected(owner: PrivateContext, cause: unknown): boolean {
		if (!current(owner)) return true;
		if (cause instanceof ApiError && cause.status === 401 && owner.scope) {
			owner.session.rejectCredentials(owner.scope);
			return true;
		}
		return false;
	}

	async function loadViewer(owner: PrivateContext): Promise<void> {
		const request = ++viewerRequest;
		viewer = { kind: 'loading' };
		try {
			if (!current(owner) || !owner.scope) return;
			const credentials = await owner.session.credentialsFor(owner.scope);
			if (!current(owner) || request !== viewerRequest) return;
			const value = await getReviewViewer(owner.spot, credentials, owner.fetcher);
			if (current(owner) && request === viewerRequest) viewer = { kind: 'ready', value };
		} catch (cause) {
			if (request !== viewerRequest || rejected(owner, cause)) return;
			viewer = {
				kind: 'error',
				message: message(cause, 'Could not load your review options. Please try again.')
			};
		}
	}

	function replacePublic(change: (review: Review) => Review): boolean {
		publicRequest++;
		if (publicState.kind !== 'ready' || publicState.spot !== spotId) return false;
		publicState = {
			...publicState,
			page: { ...publicState.page, items: publicState.page.items.map(change) },
			more: 'idle'
		};
		return true;
	}

	async function saveReview(draft: ReviewDraft): Promise<void> {
		const owner = context;
		if (!owner || !current(owner) || !owner.scope || access?.kind !== 'student' || mutation) return;
		const existing = access.own_review;
		mutation = { kind: 'review' };
		mutationError = null;
		notice = '';
		try {
			const credentials = await owner.session.credentialsFor(owner.scope);
			if (!current(owner)) return;
			const review = await (existing ? updateReview : createReview)(
				owner.spot,
				draft,
				credentials,
				owner.fetcher
			);
			if (!current(owner)) return;
			viewerRequest++;
			viewer = { kind: 'ready', value: { kind: 'student', own_review: review } };
			editor = 'closed';
			notice = existing ? 'Review updated.' : 'Review posted.';
			if (existing && replacePublic((item) => (item.id === review.id ? review : item))) {
				void refreshSummary(owner);
			} else {
				void load(owner.spot);
			}
		} catch (cause) {
			if (rejected(owner, cause)) return;
			if (!existing && cause instanceof ApiError && cause.status === 409) {
				editor = 'closed';
				await loadViewer(owner);
				if (current(owner)) {
					if (viewer.kind === 'ready')
						notice = 'Your review options were refreshed. No additional review was posted.';
					void load(owner.spot);
				}
				return;
			}
			mutationError = {
				kind: 'review',
				message: `${message(cause, 'Could not save your review.')} Your changes are still here. Try again.`
			};
		} finally {
			if (current(owner)) mutation = null;
		}
	}

	async function removeReview(): Promise<void> {
		const owner = context;
		if (
			!owner ||
			!current(owner) ||
			!owner.scope ||
			access?.kind !== 'student' ||
			!access.own_review ||
			mutation
		)
			return;
		mutation = { kind: 'review' };
		mutationError = null;
		notice = '';
		try {
			const credentials = await owner.session.credentialsFor(owner.scope);
			if (!current(owner)) return;
			await deleteReview(owner.spot, credentials, owner.fetcher);
			if (!current(owner)) return;
			viewerRequest++;
			viewer = { kind: 'ready', value: { kind: 'student', own_review: null } };
			editor = 'closed';
			notice = 'Review deleted.';
			void load(owner.spot);
		} catch (cause) {
			if (rejected(owner, cause)) return;
			mutationError = {
				kind: 'review',
				message: message(cause, 'Could not delete your review. Please try again.')
			};
		} finally {
			if (current(owner)) mutation = null;
		}
	}

	async function saveReply(reviewId: number, body: string | null): Promise<boolean> {
		const owner = context;
		if (!owner || !current(owner) || !owner.scope || access?.kind !== 'owner' || mutation)
			return false;
		mutation = { kind: 'reply', reviewId };
		mutationError = null;
		notice = '';
		try {
			const credentials = await owner.session.credentialsFor(owner.scope);
			if (!current(owner)) return false;
			let reply: ReviewReply | null;
			if (body === null) {
				await deleteReviewReply(owner.spot, reviewId, credentials, owner.fetcher);
				reply = null;
			} else {
				reply = await putReviewReply(owner.spot, reviewId, body, credentials, owner.fetcher);
			}
			if (!current(owner)) return false;
			viewerRequest++;
			replacePublic((review) => (review.id === reviewId ? { ...review, reply } : review));
			notice = body === null ? 'Reply deleted.' : 'Reply saved.';
			return true;
		} catch (cause) {
			if (!rejected(owner, cause)) {
				mutationError = {
					kind: 'reply',
					reviewId,
					message: message(cause, 'Could not save your reply. Please try again.')
				};
			}
			return false;
		} finally {
			if (current(owner)) mutation = null;
		}
	}

	$effect(() => {
		const spot = spotId;
		const network = fetcher;
		untrack(() => void load(spot, false, network));
	});

	$effect(() => {
		const spot = spotId;
		if (!publicPage || anchoredSpot === spot) return;
		const frame = window.requestAnimationFrame(() => {
			if (!alive || spot !== spotId) return;
			anchoredSpot = spot;
			if (window.location.hash === '#reviews') document.getElementById('reviews')?.scrollIntoView();
		});
		return () => window.cancelAnimationFrame(frame);
	});

	$effect.pre(() => {
		const next = {
			spot: spotId,
			session,
			scope: session.scope,
			fetcher,
			accountType: session.account?.account_type
		};
		untrack(() => {
			viewerRequest++;
			context = next;
			viewer = { kind: 'loading' };
			editor = 'closed';
			mutation = null;
			mutationError = null;
			notice = '';
			if (next.scope) void loadViewer(next);
		});
	});

	onDestroy(() => {
		alive = false;
		publicRequest++;
		viewerRequest++;
	});
</script>

<section id="reviews" class="reviews" aria-labelledby={`${id}-title`}>
	<header class="reviews-heading">
		<h2 id={`${id}-title`}>Reviews</h2>
		<p class="reviews-scale">5 is best</p>
	</header>

	{#if publicPage}
		<p class="reviews-summary">
			{#if average === null}
				<span>No ratings yet</span>
			{:else}
				<strong>{average.toFixed(1)} out of 5</strong>
			{/if}
			<span
				>{publicPage.pagination.total}
				{publicPage.pagination.total === 1 ? 'review' : 'reviews'}</span
			>
		</p>
	{/if}

	{#key context}
		{#if privateVisible}
			{#if viewer.kind === 'loading'}
				<p class="reviews-note" role="status">Loading your review options…</p>
			{:else if viewer.kind === 'error'}
				<div class="reviews-private-error">
					<p class="reviews-error" role="alert">{viewer.message}</p>
					<button type="button" onclick={() => context && loadViewer(context)}
						>Try again for your review</button
					>
				</div>
			{:else if access?.kind === 'student'}
				<div class="reviews-own" aria-labelledby={`${id}-own-title`}>
					<h3 id={`${id}-own-title`}>Your review</h3>
					{#if editor === 'write' || editor === 'edit'}
						<ReviewForm
							initial={editor === 'edit' ? ownReview : null}
							saving={mutation !== null}
							error={mutationError?.kind === 'review' ? mutationError.message : ''}
							onsubmit={saveReview}
							oncancel={() => {
								editor = 'closed';
								mutationError = null;
							}}
						/>
					{:else if ownReview}
						<ReviewCard review={ownReview}>
							{#if mutationError?.kind === 'review'}
								<p class="reviews-error" role="alert">{mutationError.message}</p>
							{/if}
							{#if editor === 'delete'}
								<p class="reviews-confirm">
									Delete your review and any owner reply? This cannot be undone.
								</p>
								<div class="reviews-actions">
									<button
										type="button"
										class="reviews-danger"
										disabled={mutation !== null}
										onclick={removeReview}>Confirm delete review</button
									>
									<button
										type="button"
										disabled={mutation !== null}
										onclick={() => (editor = 'closed')}>Cancel</button
									>
								</div>
							{:else}
								<div class="reviews-actions">
									<button type="button" onclick={() => (editor = 'edit')}>Edit review</button>
									<button type="button" onclick={() => (editor = 'delete')}>Delete review</button>
								</div>
							{/if}
						</ReviewCard>
					{:else}
						<p class="reviews-note">Share what it is like to study here.</p>
						<button type="button" onclick={() => (editor = 'write')}>Write a review</button>
					{/if}
				</div>
			{:else if session.account?.account_type === null}
				<p class="reviews-note">
					<a href={resolve(`/account?returnTo=${encodeURIComponent(returnTo)}`)}
						>Finish sign-up to write a review</a
					>
				</p>
			{/if}
			{#if notice}<p class="reviews-notice" role="status">{notice}</p>{/if}
		{:else if session.status === 'signed-out'}
			<p class="reviews-note reviews-signin">
				<a href={resolve(`/account?returnTo=${encodeURIComponent(returnTo)}`)}
					>Sign in to write a review</a
				>
			</p>
		{/if}
	{/key}

	{#if publicState.spot !== spotId || publicState.kind === 'loading'}
		<p class="reviews-note" role="status">Loading reviews…</p>
	{:else if publicState.kind === 'error'}
		<p class="reviews-error" role="alert">Could not load reviews.</p>
		<button type="button" disabled={mutation !== null} onclick={() => load(spotId)}
			>Try again</button
		>
	{:else if publicPage}
		{#if publicPage.items.length === 0}
			<p class="reviews-note">No reviews yet.</p>
		{:else if publicReviews.length > 0}
			<ul class="reviews-list" aria-label="Student reviews">
				{#each publicReviews as review (review.id)}
					<li>
						<ReviewCard {review}>
							{#if access?.kind === 'owner'}
								{#key context}
									<ReviewReplyEditor
										{review}
										busy={mutation !== null}
										error={mutationError?.kind === 'reply' && mutationError.reviewId === review.id
											? mutationError.message
											: ''}
										onsave={(body) => saveReply(review.id, body)}
										ondelete={() => saveReply(review.id, null)}
									/>
								{/key}
							{/if}
						</ReviewCard>
					</li>
				{/each}
			</ul>
		{/if}
		{#if publicState.more === 'error'}
			<p class="reviews-error" role="alert">Could not load more reviews. Please try again.</p>
		{/if}
		{#if publicPage.pagination.has_more}
			<button
				type="button"
				disabled={publicState.more === 'loading' || mutation !== null}
				onclick={() => load(spotId, true)}>Show more</button
			>
			{#if publicState.more === 'loading'}
				<p class="reviews-note" role="status">Loading more reviews…</p>
			{/if}
		{/if}
	{/if}
</section>
