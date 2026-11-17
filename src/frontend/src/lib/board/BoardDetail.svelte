<script lang="ts">
	import { onMount } from 'svelte';
	import {
		boardDate,
		boardError,
		boardUrl,
		deleteBoardPost,
		fetchBoardPost,
		kindLabels,
		reportBoardPost,
		updateBoardPost,
		type BoardAccess,
		type BoardFilters,
		type BoardPost,
		type PostDraft
	} from '$lib/board';
	import BoardComposer from './BoardComposer.svelte';
	import BoardComments from './BoardComments.svelte';
	import BoardReport from './BoardReport.svelte';
	import BoardTags from './BoardTags.svelte';

	let {
		postId,
		access,
		filters,
		ondeleted
	}: {
		postId: number;
		access: BoardAccess | null;
		filters: BoardFilters;
		ondeleted: () => Promise<void>;
	} = $props();
	let post = $state<BoardPost | null>(null);
	let loading = $state(true);
	let error = $state('');
	let editing = $state(false);
	let deleting = $state(false);
	let notice = $state('');
	let alive = true;
	let request = 0;
	onMount(() => {
		void load();
		return () => {
			alive = false;
			request++;
		};
	});

	async function load(quiet = false) {
		const current = ++request;
		if (!quiet) loading = true;
		error = '';
		try {
			const result = await fetchBoardPost(postId);
			if (alive && current === request) post = result;
		} catch (cause) {
			if (alive && current === request) error = boardError(cause);
		} finally {
			if (alive && current === request) loading = false;
		}
	}
	async function save(draft: PostDraft) {
		request++;
		const result = await updateBoardPost(postId, draft);
		if (!alive) return;
		post = result;
		editing = false;
		notice = 'Post updated.';
	}
	async function remove() {
		if (deleting || !window.confirm('Delete this post and its comments? This cannot be undone.'))
			return;
		deleting = true;
		error = '';
		try {
			await deleteBoardPost(postId);
			if (alive) await ondeleted();
		} catch (cause) {
			if (alive) error = boardError(cause);
		} finally {
			if (alive) deleting = false;
		}
	}
</script>

<a class="board-back" href={boardUrl(filters)}>Back to board</a>
{#if notice}<p role="status">{notice}</p>{/if}
{#if error}
	<div class="board-error" role="alert">
		<p>{error}</p>
		<button type="button" onclick={() => load()}>Retry post</button>
	</div>
{/if}
{#if loading}<p role="status">Loading post…</p>{/if}
{#if post}
	{#if editing && access}
		<BoardComposer {access} initial={post} onsubmit={save} oncancel={() => (editing = false)} />
	{:else}
		<article class="board-detail" data-post-id={post.id} aria-label="Board post">
			<p class="board-meta"><span>{kindLabels[post.kind]}</span></p>
			<h1>{post.title}</h1>
			<p class="board-meta">
				<strong>{post.author.name}</strong>
				<span>{post.author.kind}</span>
				<time datetime={post.created_at}>{boardDate(post.created_at)}</time>
			</p>
			<BoardTags tags={post.tags} {filters} />
			<p class="board-body">{post.body}</p>
			<div class="board-actions">
				{#if post.can_edit && access}<button
						type="button"
						disabled={deleting}
						onclick={() => (editing = true)}>Edit post</button
					>{/if}
				{#if post.can_delete}<button type="button" disabled={deleting} onclick={remove}
						>{deleting ? 'Deleting post…' : 'Delete post'}</button
					>{/if}
			</div>
			{#if post.can_report && access?.can_report}
				<BoardReport
					target="post"
					limit={access.limits.reason}
					onsubmit={(reason) => reportBoardPost(postId, reason)}
				/>
			{/if}
		</article>
		<BoardComments {postId} {access} onchange={() => void load(true)} />
	{/if}
{/if}
