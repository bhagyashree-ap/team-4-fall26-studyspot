<script lang="ts">
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { onMount } from 'svelte';
	import {
		boardDate,
		boardError,
		boardFilters,
		boardUrl,
		createBoardPost,
		fetchBoardAccess,
		fetchBoardPosts,
		fetchBoardTags,
		kindLabels,
		type BoardAccess,
		type BoardFilters,
		type BoardPost,
		type PostDraft,
		type TagSuggestion
	} from '$lib/board';
	import BoardComposer from './BoardComposer.svelte';
	import BoardDetail from './BoardDetail.svelte';
	import BoardTags from './BoardTags.svelte';

	const id = $props.id();
	const filters = $derived(boardFilters(page.url));
	const postParam = $derived(page.url.searchParams.get('post'));
	const postId = $derived(postParam && /^[1-9]\d*$/.test(postParam) ? Number(postParam) : null);
	const composing = $derived(page.url.searchParams.get('compose') === '1' && postParam === null);
	let access = $state<BoardAccess | null>(null);
	let initialized = $state(false);
	let accessLoading = $state(true);
	let accessError = $state('');
	let posts = $state<BoardPost[]>([]);
	let hasMore = $state(false);
	let loading = $state(true);
	let error = $state('');
	let notice = $state('');
	let q = $state('');
	let subject = $state('');
	let university = $state('');
	let spot = $state('');
	let kind = $state('');
	let spotQuery = $state('');
	let spotOptions = $state<TagSuggestion[]>([]);
	let spotLoading = $state(false);
	let spotError = $state('');
	let alive = true;
	let request = 0;
	let tagRequest = 0;

	onMount(() => {
		void loadAccess();
		return () => {
			alive = false;
			request++;
			tagRequest++;
		};
	});

	$effect(() => {
		const current = filters;
		q = current.q;
		subject = current.subject;
		university = current.university;
		spot = current.spot;
		kind = current.kind;
	});
	$effect(() => {
		if (initialized && postParam === null && !composing) void loadPosts(filters);
	});
	$effect(() => {
		const query = spotQuery.trim();
		if (!initialized) return;
		const current = ++tagRequest;
		spotLoading = true;
		spotError = '';
		const timer = setTimeout(async () => {
			try {
				const result = await fetchBoardTags('spot', query);
				if (alive && current === tagRequest) spotOptions = result.items;
			} catch (cause) {
				if (alive && current === tagRequest) spotError = boardError(cause);
			} finally {
				if (alive && current === tagRequest) spotLoading = false;
			}
		}, 250);
		return () => clearTimeout(timer);
	});

	async function loadAccess() {
		accessLoading = true;
		accessError = '';
		try {
			const result = await fetchBoardAccess();
			if (alive) access = result;
		} catch (cause) {
			if (alive) accessError = boardError(cause);
		} finally {
			if (alive) {
				accessLoading = false;
				initialized = true;
			}
		}
	}
	async function loadPosts(current: BoardFilters, more = false) {
		const generation = ++request;
		loading = true;
		error = '';
		if (!more) posts = [];
		try {
			const result = await fetchBoardPosts(current, more ? posts.at(-1)?.id : undefined);
			if (!alive || generation !== request) return;
			posts = more ? [...posts, ...result.items] : result.items;
			hasMore = result.has_more;
		} catch (cause) {
			if (alive && generation === request) error = boardError(cause);
		} finally {
			if (alive && generation === request) loading = false;
		}
	}
	async function apply(event: SubmitEvent) {
		event.preventDefault();
		notice = '';
		await goto(boardUrl({ q, subject, university, spot, kind }), { keepFocus: true });
	}
	async function publish(draft: PostDraft) {
		const post = await createBoardPost(draft);
		if (!alive) return;
		notice = 'Post published.';
		await goto(boardUrl(filters, post.id));
	}
	async function deleted() {
		notice = 'Post deleted.';
		await goto(boardUrl(filters));
	}
</script>

{#if accessLoading}<p role="status">Checking board access…</p>{/if}
{#if accessError}
	<div class="board-error" role="alert">
		<p>{accessError} You can still browse public posts.</p>
		<button type="button" onclick={loadAccess}>Retry board access</button>
	</div>
{/if}
{#if notice}<p role="status">{notice}</p>{/if}
{#if postParam !== null}
	{#if postId && Number.isSafeInteger(postId)}
		{#key postId}<BoardDetail {postId} {access} {filters} ondeleted={deleted} />{/key}
	{:else}
		<h1>Post not found</h1>
		<p>This post link is not valid.</p>
		<a class="board-back" href={boardUrl(filters)}>Back to board</a>
	{/if}
{:else if composing}
	<a class="board-back" href={boardUrl(filters)}>Back to board</a>
	{#if access?.create_kinds.length}
		<BoardComposer {access} onsubmit={publish} oncancel={() => void goto(boardUrl(filters))} />
	{:else if !accessLoading}
		<h1>New post</h1>
		<p>Publishing is not available for your current session.</p>
	{/if}
{:else}
	<div class="board-heading">
		<div>
			<h1>Public board</h1>
			<p class="board-muted">Ask questions, share information, and discuss study spots.</p>
		</div>
		{#if access?.create_kinds.length}<a class="board-primary" href={boardUrl(filters, 'compose')}
				>New post</a
			>{/if}
	</div>
	{#if access?.viewer === 'guest'}
		<p class="board-help">
			Posting as a guest. Keep this browser's cookies to manage your posts and comments.
		</p>
	{:else if access && !access.create_kinds.length}
		<p class="board-help">
			Public posts are open to everyone. Publishing is not available for your current session.
			{#if access.viewer === 'unfinished'}<a href={resolve('/account')}>Complete your account</a> to post.{/if}
		</p>
	{/if}
	<form class="board-filters" aria-label="Filter board posts" onsubmit={apply}>
		<div class="board-field board-keyword">
			<label for={`${id}-q`}>Search posts</label>
			<input id={`${id}-q`} type="search" bind:value={q} placeholder="Search titles and messages" />
		</div>
		<div class="board-field">
			<label for={`${id}-subject`}>Subject filter</label>
			<input id={`${id}-subject`} bind:value={subject} maxlength="80" placeholder="Any subject" />
		</div>
		<div class="board-field">
			<label for={`${id}-university`}>University filter</label>
			<input
				id={`${id}-university`}
				bind:value={university}
				maxlength="120"
				placeholder="Any university"
			/>
		</div>
		<div class="board-field">
			<label for={`${id}-kind`}>Post type filter</label>
			<select id={`${id}-kind`} bind:value={kind}>
				<option value="">All post types</option>
				<option value="question">Question</option>
				<option value="information">Information</option>
				<option value="announcement">Announcement</option>
			</select>
		</div>
		<div class="board-field">
			<label for={`${id}-spot-query`}>Find a study spot tag</label>
			<input
				id={`${id}-spot-query`}
				bind:value={spotQuery}
				type="search"
				placeholder="Search used spot tags"
			/>
		</div>
		<div class="board-field">
			<label for={`${id}-spot`}>Study spot filter</label>
			<select id={`${id}-spot`} bind:value={spot}>
				<option value="">All study spots</option>
				{#if spot && !spotOptions.some((tag) => tag.value === spot)}<option value={spot}
						>Selected study spot</option
					>{/if}
				{#each spotOptions as tag (tag.value)}<option value={tag.value}
						>{tag.label}{!tag.available ? ' (no longer listed)' : ''}</option
					>{/each}
			</select>
		</div>
		<div class="board-actions board-filter-actions">
			<button class="board-primary" type="submit">Apply filters</button>
			<a class="board-button" href={boardUrl()}>Clear filters</a>
		</div>
		{#if spotLoading}<p class="board-help" role="status">Loading study spot tags…</p>{/if}
		{#if spotError}<p class="board-error" role="alert">
				{spotError} Search again to retry spot tags.
			</p>{/if}
	</form>
	<section aria-label="Board posts" aria-busy={loading}>
		{#if error}
			<div class="board-error" role="alert">
				<p>{error}</p>
				<button type="button" onclick={() => loadPosts(filters, posts.length > 0)}
					>Retry posts</button
				>
			</div>
		{/if}
		{#if loading}<p role="status">Loading posts…</p>{/if}
		<ol class="board-feed">
			{#each posts as post (post.id)}
				<li>
					<article class="board-feed-post" data-post-id={post.id}>
						<p class="board-meta">
							<span>{kindLabels[post.kind]}</span><span
								>{post.comment_count} {post.comment_count === 1 ? 'comment' : 'comments'}</span
							>
						</p>
						<h2><a href={boardUrl(filters, post.id)}>{post.title}</a></h2>
						<p class="board-meta">
							<strong>{post.author.name}</strong><span>{post.author.kind}</span><time
								datetime={post.created_at}>{boardDate(post.created_at)}</time
							>
						</p>
						<p class="board-body board-preview">{post.body}</p>
						<BoardTags tags={post.tags} {filters} />
					</article>
				</li>
			{/each}
		</ol>
		{#if !loading && !error && !posts.length}
			<div class="board-empty">
				<h2>{Object.values(filters).some(Boolean) ? 'No matching posts' : 'No posts yet'}</h2>
				<p>
					{Object.values(filters).some(Boolean)
						? 'Try another keyword or clear your filters.'
						: 'Start a discussion by asking a question or sharing information.'}
				</p>
			</div>
		{/if}
		{#if hasMore && posts.length}<button
				type="button"
				disabled={loading}
				onclick={() => loadPosts(filters, true)}>{loading ? 'Loading…' : 'Load more posts'}</button
			>{/if}
	</section>
{/if}
