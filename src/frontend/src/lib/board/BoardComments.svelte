<script lang="ts">
	import { onMount } from 'svelte';
	import {
		boardDate,
		boardError,
		createBoardComment,
		deleteBoardComment,
		fetchBoardComments,
		reportBoardComment,
		updateBoardComment,
		type BoardAccess,
		type BoardComment
	} from '$lib/board';
	import BoardReport from './BoardReport.svelte';

	let {
		postId,
		access,
		onchange
	}: { postId: number; access: BoardAccess | null; onchange: () => void } = $props();
	const id = $props.id();
	let comments = $state<BoardComment[]>([]);
	let hasMore = $state(false);
	let loading = $state(true);
	let loadError = $state('');
	let mutationError = $state('');
	let draft = $state('');
	let sending = $state(false);
	let editing = $state<number | null>(null);
	let editBody = $state('');
	let mutating = $state<number | null>(null);
	let notice = $state('');
	let cursor: number | undefined;
	let alive = true;
	let request = 0;

	onMount(() => {
		void load();
		return () => {
			alive = false;
			request++;
		};
	});

	async function load(more = false) {
		const current = ++request;
		loading = true;
		loadError = '';
		try {
			const result = await fetchBoardComments(postId, more ? cursor : undefined);
			if (!alive || current !== request) return;
			const combined = more ? [...comments, ...result.items] : result.items;
			comments = [...new Map(combined.map((comment) => [comment.id, comment])).values()].sort(
				(a, b) => a.id - b.id
			);
			cursor = result.items.at(-1)?.id ?? cursor;
			hasMore = result.has_more;
		} catch (cause) {
			if (alive && current === request) loadError = boardError(cause);
		} finally {
			if (alive && current === request) loading = false;
		}
	}

	async function send(event: SubmitEvent) {
		event.preventDefault();
		if (sending || loading || !draft.trim() || !access?.can_comment) return;
		sending = true;
		mutationError = '';
		notice = '';
		try {
			const comment = await createBoardComment(postId, draft);
			if (!alive) return;
			comments = [...comments, comment].sort((a, b) => a.id - b.id);
			draft = '';
			notice = 'Comment posted.';
			onchange();
		} catch (cause) {
			if (alive)
				mutationError = `${boardError(cause)} Your comment is still here. Please try again.`;
		} finally {
			if (alive) sending = false;
		}
	}

	async function save(event: SubmitEvent, comment: BoardComment) {
		event.preventDefault();
		if (mutating !== null || !editBody.trim()) return;
		mutating = comment.id;
		mutationError = '';
		try {
			const updated = await updateBoardComment(comment.id, editBody);
			if (!alive) return;
			request++;
			loading = false;
			comments = comments.map((item) => (item.id === updated.id ? updated : item));
			editing = null;
			notice = 'Comment updated.';
		} catch (cause) {
			if (alive)
				mutationError = `${boardError(cause)} Your changes are still here. Please try again.`;
		} finally {
			if (alive) mutating = null;
		}
	}

	async function remove(comment: BoardComment) {
		if (mutating !== null || !window.confirm('Delete this comment? This cannot be undone.')) return;
		mutating = comment.id;
		mutationError = '';
		try {
			await deleteBoardComment(comment.id);
			if (!alive) return;
			request++;
			loading = false;
			comments = comments.filter((item) => item.id !== comment.id);
			if (editing === comment.id) editing = null;
			notice = 'Comment deleted.';
			onchange();
		} catch (cause) {
			if (alive) mutationError = boardError(cause);
		} finally {
			if (alive) mutating = null;
		}
	}
</script>

<section class="board-comments" aria-labelledby={`${id}-heading`}>
	<h2 id={`${id}-heading`}>Comments</h2>
	{#if mutationError}<p class="board-error" role="alert">{mutationError}</p>{/if}
	{#if notice}<p role="status">{notice}</p>{/if}
	<ol class="board-comment-list" aria-label="Comments">
		{#each comments as comment (comment.id)}
			<li>
				<article
					class="board-comment"
					data-comment-id={comment.id}
					aria-label={`Comment by ${comment.author.name}`}
				>
					<p class="board-meta">
						<strong>{comment.author.name}</strong>
						<span>{comment.author.kind}</span>
						<time datetime={comment.created_at}>{boardDate(comment.created_at)}</time>
					</p>
					{#if editing === comment.id}
						<form aria-label="Edit comment" onsubmit={(event) => save(event, comment)}>
							<div class="board-field">
								<label for={`${id}-edit-${comment.id}`}>Edit comment</label>
								<textarea
									id={`${id}-edit-${comment.id}`}
									bind:value={editBody}
									maxlength={access?.limits.comment ?? 3000}
									rows="4"
									required
									disabled={mutating !== null}></textarea>
							</div>
							<div class="board-actions">
								<button type="submit" disabled={mutating !== null}
									>{mutating === comment.id ? 'Saving comment…' : 'Save comment'}</button
								>
								<button type="button" disabled={mutating !== null} onclick={() => (editing = null)}
									>Cancel edit</button
								>
							</div>
						</form>
					{:else}
						<p class="board-body">{comment.body}</p>
					{/if}
					<div class="board-actions">
						{#if comment.can_edit && editing !== comment.id}
							<button
								type="button"
								disabled={mutating !== null}
								onclick={() => {
									editing = comment.id;
									editBody = comment.body;
									mutationError = '';
								}}>Edit comment</button
							>
						{/if}
						{#if comment.can_delete}<button
								type="button"
								disabled={mutating !== null}
								onclick={() => remove(comment)}
								>{mutating === comment.id ? 'Working…' : 'Delete comment'}</button
							>{/if}
					</div>
					{#if comment.can_report && access?.can_report}
						<BoardReport
							target="comment"
							limit={access.limits.reason}
							onsubmit={(reason) => reportBoardComment(comment.id, reason)}
						/>
					{/if}
				</article>
			</li>
		{/each}
	</ol>
	{#if loading}<p role="status">Loading comments…</p>{/if}
	{#if loadError}
		<div class="board-error" role="alert">
			<p>{loadError}</p>
			<button type="button" onclick={() => load(comments.length > 0)}>Retry comments</button>
		</div>
	{:else if !loading && !comments.length}
		<p class="board-muted">No comments yet. Add to the discussion below.</p>
	{/if}
	{#if hasMore}<button type="button" disabled={loading} onclick={() => load(true)}
			>Load more comments</button
		>{/if}
	{#if access?.can_comment}
		<form class="board-comment-composer" aria-label="Add comment" onsubmit={send}>
			<div class="board-field">
				<label for={`${id}-draft`}>Your comment</label>
				<textarea
					id={`${id}-draft`}
					bind:value={draft}
					maxlength={access.limits.comment}
					rows="4"
					required
					disabled={sending}></textarea>
			</div>
			<button class="board-primary" type="submit" disabled={sending || loading || !draft.trim()}
				>{sending ? 'Posting comment…' : 'Post comment'}</button
			>
		</form>
	{:else}
		<p class="board-help">Commenting is not available for your current session.</p>
	{/if}
</section>
