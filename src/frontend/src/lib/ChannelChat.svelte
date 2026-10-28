<script lang="ts">
	import { tick } from 'svelte';
	import {
		communityRequest,
		type Channel,
		type DirectConversation,
		type Message
	} from './communities';

	let {
		communityId,
		channel,
		role,
		onDirectMessage
	}: {
		communityId: number;
		channel: Channel;
		role: string;
		onDirectMessage: (conversation: DirectConversation) => void;
	} = $props();

	let messages = $state<Message[]>([]);
	let hasOlder = $state(false);
	let content = $state('');
	let replyTo = $state<Message | null>(null);
	let editingId = $state<number | null>(null);
	let draft = $state('');
	let reactionFor = $state<number | null>(null);
	let showSearch = $state(false);
	let search = $state('');
	let results = $state<Message[] | null>(null);
	let showPinsPanel = $state(false);
	let pins = $state<Message[] | null>(null);
	let error = $state('');
	let sending = $state(false);
	let polling = false;
	let generation = 0;
	let messageList = $state<HTMLDivElement>();
	let composeEl = $state<HTMLTextAreaElement>();
	let prevMsgCount = 0;

	const emojiChoices = ['👍', '❤️', '😂', '🎉', '😮', '🔥', '😢'];

	const base = () => `/communities/${communityId}/channels/${channel.id}`;
	const problem = (cause: unknown) =>
		cause instanceof Error ? cause.message : 'Something went wrong.';

	function formatTime(iso: string): string {
		const d = new Date(iso);
		const now = new Date();
		const todayMs = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
		const yestMs = todayMs - 86_400_000;
		const dMs = new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
		const time = d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
		if (dMs === todayMs) return `Today at ${time}`;
		if (dMs === yestMs) return `Yesterday at ${time}`;
		return d.toLocaleDateString([], { month: 'short', day: 'numeric' }) + ` at ${time}`;
	}

	function formatDate(iso: string): string {
		const d = new Date(iso);
		const now = new Date();
		const todayMs = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
		const yestMs = todayMs - 86_400_000;
		const dMs = new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
		if (dMs === todayMs) return 'Today';
		if (dMs === yestMs) return 'Yesterday';
		return d.toLocaleDateString([], { weekday: 'long', month: 'long', day: 'numeric' });
	}

	function showHeader(i: number): boolean {
		if (i === 0) return true;
		const prev = messages[i - 1];
		const curr = messages[i];
		if (prev.deleted_at || prev.author_name !== curr.author_name) return true;
		return new Date(curr.created_at).getTime() - new Date(prev.created_at).getTime() > 5 * 60_000;
	}

	function showDateSep(i: number): boolean {
		if (i === 0) return true;
		const prev = messages[i - 1];
		const curr = messages[i];
		const prevDay = new Date(prev.created_at);
		const currDay = new Date(curr.created_at);
		return (
			prevDay.getFullYear() !== currDay.getFullYear() ||
			prevDay.getMonth() !== currDay.getMonth() ||
			prevDay.getDate() !== currDay.getDate()
		);
	}

	function initials(name: string): string {
		return (
			name
				.split(/\s+/)
				.slice(0, 2)
				.map((w) => w[0] ?? '')
				.join('')
				.toUpperCase() || '?'
		);
	}

	const palette = ['#9b1c3a', '#eb459e', '#3ba55c', '#faa61a', '#9b59b6', '#1abc9c', '#e67e22'];
	function avatarColor(name: string): string {
		let h = 0;
		for (const c of name) h = (h * 31 + c.charCodeAt(0)) | 0;
		return palette[Math.abs(h) % palette.length];
	}

	function replyPreview(id: number): string {
		const msg = messages.find((m) => m.id === id);
		if (!msg) return `Message #${id}`;
		if (msg.deleted_at) return 'Original message was deleted';
		return msg.content.slice(0, 100) + (msg.content.length > 100 ? '…' : '');
	}

	function replyAuthor(id: number): string {
		return messages.find((m) => m.id === id)?.author_name ?? 'Unknown';
	}

	async function scrollToBottom() {
		await tick();
		if (messageList) messageList.scrollTop = messageList.scrollHeight;
	}

	async function load() {
		const current = ++generation;
		try {
			const page = await communityRequest<{ items: Message[]; has_more: boolean }>(
				`${base()}/messages`
			);
			if (current !== generation) return;
			messages = page.items;
			hasOlder = page.has_more;
			error = '';
			await scrollToBottom();
		} catch (cause) {
			if (current === generation) error = problem(cause);
		}
	}

	async function refresh() {
		if (polling || document.visibilityState !== 'visible') return;
		polling = true;
		const current = generation;
		try {
			const page = await communityRequest<{ items: Message[]; has_more: boolean }>(
				`${base()}/messages`
			);
			if (current === generation) {
				const first = page.items[0]?.id;
				const retained = first ? messages.filter((item) => item.id < first) : [];
				const older = retained.slice(-200);
				const hadNew = page.items.some((m) => !messages.find((e) => e.id === m.id));
				messages = [...older, ...page.items];
				hasOlder ||= retained.length > older.length;
				if (hadNew) await scrollToBottom();
			}
		} catch (cause) {
			if (current === generation) error = problem(cause);
		} finally {
			polling = false;
		}
	}

	async function older() {
		if (!messages.length) return;
		const scrollEl = messageList;
		const prevScrollHeight = scrollEl?.scrollHeight ?? 0;
		try {
			const page = await communityRequest<{ items: Message[]; has_more: boolean }>(
				`${base()}/messages?before=${messages[0].id}`
			);
			messages = [...page.items, ...messages];
			hasOlder = page.has_more;
			await tick();
			if (scrollEl) scrollEl.scrollTop = scrollEl.scrollHeight - prevScrollHeight;
		} catch (cause) {
			error = problem(cause);
		}
	}

	async function send() {
		if (!content.trim() || sending) return;
		sending = true;
		const body = { content: content.trim(), ...(replyTo ? { reply_to: replyTo.id } : {}) };
		try {
			const message = await communityRequest<Message>(`${base()}/messages`, 'POST', body);
			messages = [...messages, message];
			content = '';
			replyTo = null;
			error = '';
			await tick();
			if (composeEl) composeEl.style.height = 'auto';
			await scrollToBottom();
		} catch (cause) {
			error = problem(cause);
		} finally {
			sending = false;
		}
	}

	async function change(message: Message, method: string, suffix = '', body?: object) {
		try {
			const changed = await communityRequest<Message>(
				`${base()}/messages/${message.id}${suffix}`,
				method,
				body
			);
			if (method === 'DELETE' && !suffix) {
				messages = messages.map((item) =>
					item.id === message.id
						? { ...item, content: '', deleted_at: new Date().toISOString(), reactions: [], pinned_at: null }
						: item
				);
			} else {
				messages = messages.map((item) => (item.id === changed.id ? changed : item));
			}
			if (method === 'PATCH') editingId = null;
			reactionFor = null;
			error = '';
		} catch (cause) {
			error = problem(cause);
		}
	}

	async function find() {
		if (search.trim().length < 2) return;
		try {
			const found = await communityRequest<{ items: Message[] }>(
				`/communities/${communityId}/messages/search?q=${encodeURIComponent(search.trim())}`
			);
			results = found.items;
			pins = null;
			error = '';
		} catch (cause) {
			error = problem(cause);
		}
	}

	async function loadPins() {
		try {
			pins = (await communityRequest<{ items: Message[] }>(`${base()}/pins`)).items;
			results = null;
			showPinsPanel = true;
		} catch (cause) {
			error = problem(cause);
		}
	}

	function closeOverlay() {
		results = null;
		pins = null;
		showSearch = false;
		showPinsPanel = false;
	}

	async function startDM(message: Message) {
		try {
			const conversation = await communityRequest<DirectConversation>(
				`${base()}/messages/${message.id}/dm`,
				'POST'
			);
			onDirectMessage(conversation);
		} catch (cause) {
			error = problem(cause);
		}
	}

	function handleCompose(e: KeyboardEvent) {
		if (e.key === 'Enter' && !e.shiftKey) {
			e.preventDefault();
			void send();
		}
		if (e.key === 'Escape' && replyTo) replyTo = null;
	}

	function resizeCompose() {
		if (!composeEl) return;
		composeEl.style.height = 'auto';
		composeEl.style.height = Math.min(composeEl.scrollHeight, 200) + 'px';
	}

	$effect(() => {
		void communityId;
		void channel.id;
		messages = [];
		hasOlder = false;
		results = pins = null;
		showSearch = false;
		showPinsPanel = false;
		prevMsgCount = 0;
		void load();
		const timer = window.setInterval(() => void refresh(), 3000);
		return () => {
			window.clearInterval(timer);
			generation++;
		};
	});
</script>

<div class="chat">
	<div class="chat-header">
		<span class="hash" aria-hidden="true">#</span>
		<strong class="channel-title">{channel.name}</strong>
		{#if channel.archived}<span class="archived-badge">Archived</span>{/if}
		<div class="header-actions">
			<button
				class="icon-btn"
				class:active={showSearch}
				aria-label="Search messages"
				title="Search"
				onclick={() => {
					showSearch = !showSearch;
					if (!showSearch) { search = ''; results = null; }
					pins = null;
					showPinsPanel = false;
				}}
			>
				<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
			</button>
			<button
				class="icon-btn"
				class:active={showPinsPanel}
				aria-label="Pinned messages"
				title="Pins"
				onclick={() => { void loadPins(); showSearch = false; }}
			>
				<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>
			</button>
		</div>
	</div>

	{#if showSearch}
		<form
			class="search-bar"
			onsubmit={(e) => { e.preventDefault(); void find(); }}
		>
			<input
				aria-label="Search messages in this channel"
				placeholder="Search messages…"
				bind:value={search}
				autofocus
			/>
			<button type="submit">Search</button>
			<button type="button" onclick={closeOverlay}>✕</button>
		</form>
	{/if}

	{#if error}<p class="error" role="alert">{error}</p>{/if}

	{#if results !== null || (pins !== null && showPinsPanel)}
		<div class="overlay-panel">
			<div class="overlay-header">
				<h4>{results !== null ? 'Search results' : 'Pinned messages'}</h4>
				<button class="icon-btn" onclick={closeOverlay} aria-label="Close">✕</button>
			</div>
			<div class="overlay-list">
				{#each results ?? pins ?? [] as item (item.id)}
					<div class="overlay-message">
						<div class="overlay-meta">
							<strong>{item.author_name}</strong>
							<time>{formatTime(item.created_at)}</time>
						</div>
						<p>{item.content}</p>
					</div>
				{:else}
					<p class="empty">No messages found.</p>
				{/each}
			</div>
		</div>
	{:else}
		<div class="messages" bind:this={messageList} aria-live="polite">
			{#if hasOlder}
				<button class="load-older" onclick={() => void older()}>Load older messages</button>
			{/if}
			{#if !messages.length && !hasOlder}
				<div class="channel-start">
					<div class="channel-start-icon" style="background:{avatarColor(channel.name)}">
						<span>#</span>
					</div>
					<h3>Welcome to #{channel.name}</h3>
					<p>This is the beginning of the #{channel.name} channel.</p>
				</div>
			{/if}
			{#each messages as message, i (message.id)}
				{@const header = showHeader(i)}
				{#if showDateSep(i)}
					<div class="date-sep"><span>{formatDate(message.created_at)}</span></div>
				{/if}
				<article
					class="message"
					class:grouped={!header}
					class:deleted={!!message.deleted_at}
					id={`msg-${message.id}`}
				>
					{#if header}
						<div class="avatar" style="background:{avatarColor(message.author_name)}" aria-hidden="true">
							{initials(message.author_name)}
						</div>
					{:else}
						<div class="avatar-gap" aria-hidden="true">
							<time class="hover-time">{new Date(message.created_at).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}</time>
						</div>
					{/if}
					<div class="msg-body">
						{#if header}
							<div class="msg-head">
								<strong class="author">{message.author_name}</strong>
								<time class="timestamp" datetime={message.created_at}>{formatTime(message.created_at)}</time>
								{#if message.pinned_at}<span class="pin-badge">📌</span>{/if}
							</div>
						{/if}
						{#if message.reply_to}
							<div class="reply-preview">
								<span class="reply-author">{replyAuthor(message.reply_to)}</span>
								<span class="reply-text">{replyPreview(message.reply_to)}</span>
							</div>
						{/if}
						{#if editingId === message.id}
							<form
								class="edit-form"
								onsubmit={(e) => { e.preventDefault(); void change(message, 'PATCH', '', { content: draft }); }}
							>
								<textarea
									aria-label="Edit message"
									maxlength="2000"
									bind:value={draft}
									rows="2"
									onkeydown={(e) => {
										if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void change(message, 'PATCH', '', { content: draft }); }
										if (e.key === 'Escape') editingId = null;
									}}
								></textarea>
								<div class="edit-actions">
									<span class="hint">Enter to save · Escape to cancel</span>
									<button disabled={!draft.trim()}>Save</button>
									<button type="button" onclick={() => (editingId = null)}>Cancel</button>
								</div>
							</form>
						{:else}
							<p class="msg-content">
								{message.deleted_at
									? 'This message was deleted.'
									: message.content}{message.edited_at && !message.deleted_at ? ' (edited)' : ''}
							</p>
						{/if}
						{#if message.reactions.length}
							<div class="reactions">
								{#each message.reactions as reaction (reaction.emoji)}
									<button
										class="reaction"
										class:reacted={reaction.me}
										onclick={() => void change(
											message,
											reaction.me ? 'DELETE' : 'POST',
											`/reactions${reaction.me ? `/${encodeURIComponent(reaction.emoji)}` : ''}`,
											reaction.me ? undefined : { emoji: reaction.emoji }
										)}
									>{reaction.emoji} <span>{reaction.count}</span></button>
								{/each}
							</div>
						{/if}
					</div>

					{#if !message.deleted_at}
						<div class="msg-actions" role="toolbar" aria-label="Message actions">
							<button
								class="action-btn"
								title="Add reaction"
								onclick={() => (reactionFor = reactionFor === message.id ? null : message.id)}
							>😊</button>
							<button class="action-btn" title="Reply" onclick={() => (replyTo = message)}>↩</button>
							{#if !message.mine}
								<button class="action-btn" title="Direct message" onclick={() => void startDM(message)}>✉</button>
							{/if}
							{#if message.mine}
								<button class="action-btn" title="Edit message" onclick={() => { editingId = message.id; draft = message.content; }}>✏</button>
							{/if}
							{#if role === 'owner' || role === 'moderator'}
								<button
									class="action-btn"
									title={message.pinned_at ? 'Unpin' : 'Pin message'}
									onclick={() => void change(message, message.pinned_at ? 'DELETE' : 'POST', '/pin')}
								>{message.pinned_at ? '📌' : '📍'}</button>
							{/if}
							{#if message.can_delete}
								<button
									class="action-btn danger"
									title="Delete message"
									onclick={() => { if (confirm('Delete this message?')) void change(message, 'DELETE'); }}
								>🗑</button>
							{/if}
						</div>
					{/if}
				</article>
				{#if reactionFor === message.id}
					<div class="emoji-picker" role="toolbar" aria-label="Reaction picker">
						{#each emojiChoices as emoji (emoji)}
							<button onclick={() => void change(message, 'POST', '/reactions', { emoji })}>{emoji}</button>
						{/each}
						<button onclick={() => (reactionFor = null)}>✕</button>
					</div>
				{/if}
			{/each}
		</div>

		{#if replyTo}
			<div class="reply-bar">
				<span class="reply-bar-icon">↩</span>
				<span>Replying to <strong>{replyTo.author_name}</strong> — {replyTo.content.slice(0, 60)}{replyTo.content.length > 60 ? '…' : ''}</span>
				<button onclick={() => (replyTo = null)} aria-label="Cancel reply">✕</button>
			</div>
		{/if}

		<div class="composer" class:archived={channel.archived}>
			<textarea
				bind:this={composeEl}
				aria-label={channel.archived ? 'Channel is archived' : `Message #${channel.name}`}
				placeholder={channel.archived ? 'This channel is archived.' : `Message #${channel.name}`}
				maxlength="2000"
				rows="1"
				bind:value={content}
				disabled={channel.archived}
				onkeydown={handleCompose}
				oninput={resizeCompose}
			></textarea>
			<button
				class="send-btn"
				disabled={channel.archived || sending || !content.trim()}
				onclick={() => void send()}
				aria-label="Send message"
			>
				<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>
			</button>
		</div>
	{/if}
</div>

<style>
	.chat {
		display: flex;
		flex-direction: column;
		flex: 1;
		min-height: 0;
		background: #fff;
	}

	/* ── Header ── */
	.chat-header {
		display: flex;
		align-items: center;
		gap: 8px;
		height: 48px;
		padding: 0 16px;
		border-bottom: 1px solid #ebebed;
		flex-shrink: 0;
		background: #fff;
	}
	.hash {
		color: #8a8490;
		font-size: 18px;
		font-weight: 700;
		line-height: 1;
	}
	.channel-title {
		font-size: 15px;
		font-weight: 700;
		color: #0f0d10;
	}
	.archived-badge {
		font-size: 11px;
		background: #f3f2f5;
		color: #8a8490;
		border-radius: 4px;
		padding: 2px 6px;
	}
	.header-actions {
		display: flex;
		gap: 4px;
		margin-left: auto;
	}
	.icon-btn {
		display: grid;
		place-items: center;
		width: 32px;
		height: 32px;
		border: 0;
		background: transparent;
		border-radius: 8px;
		color: #8a8490;
		cursor: pointer;
		transition: background 0.12s, color 0.12s;
		padding: 0;
		min-height: 0;
		font-size: 14px;
	}
	.icon-btn:hover {
		background: #f3f2f5;
		color: #0f0d10;
	}
	.icon-btn.active {
		background: #fdf2f5;
		color: #9b1c3a;
	}

	/* ── Search bar ── */
	.search-bar {
		display: flex;
		gap: 8px;
		padding: 8px 16px;
		border-bottom: 1px solid #ebebed;
		background: #f9f8fa;
		flex-shrink: 0;
		animation: slideDown 0.15s ease;
	}
	.search-bar input {
		flex: 1;
		border: 1px solid #d4d2d8;
		border-radius: 8px;
		padding: 7px 10px;
		font: inherit;
		font-size: 14px;
		background: #fff;
		color: #0f0d10;
	}
	.search-bar input:focus {
		outline: none;
		border-color: #9b1c3a;
		box-shadow: 0 0 0 3px rgba(155,28,58,0.10);
	}
	.search-bar button {
		cursor: pointer;
		border: 1px solid #d4d2d8;
		border-radius: 8px;
		background: #fff;
		padding: 7px 12px;
		font: inherit;
		font-size: 13px;
		font-weight: 600;
		transition: background 0.1s;
		color: #4a4550;
	}
	.search-bar button:hover { background: #f3f2f5; }

	/* ── Overlay (search results / pins) ── */
	.overlay-panel {
		display: flex;
		flex-direction: column;
		flex: 1;
		min-height: 0;
	}
	.overlay-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 12px 20px;
		border-bottom: 1px solid #ebebed;
		flex-shrink: 0;
	}
	.overlay-header h4 {
		margin: 0;
		font-size: 14px;
		font-weight: 700;
		color: #0f0d10;
	}
	.overlay-list {
		flex: 1;
		min-height: 0;
		overflow-y: auto;
		padding: 8px 20px;
	}
	.overlay-message {
		padding: 10px 0;
		border-bottom: 1px solid #f3f2f5;
	}
	.overlay-meta {
		display: flex;
		gap: 10px;
		align-items: baseline;
		margin-bottom: 4px;
	}
	.overlay-meta strong { font-size: 14px; color: #0f0d10; }
	.overlay-meta time { font-size: 11px; color: #8a8490; }
	.overlay-message p { margin: 0; font-size: 14px; color: #4a4550; }
	.empty { color: #8a8490; font-size: 14px; }

	/* ── Messages list ── */
	.messages {
		flex: 1;
		min-height: 0;
		overflow-y: auto;
		padding: 16px 0 4px;
		scroll-behavior: smooth;
	}

	/* Date separator */
	.date-sep {
		display: flex;
		align-items: center;
		gap: 12px;
		padding: 12px 20px 4px;
		color: #8a8490;
		font-size: 12px;
		font-weight: 600;
	}
	.date-sep::before,
	.date-sep::after {
		content: '';
		flex: 1;
		height: 1px;
		background: #ebebed;
	}
	.date-sep span {
		white-space: nowrap;
		padding: 0 2px;
	}

	.channel-start {
		padding: 24px 20px 20px;
		text-align: left;
	}
	.channel-start-icon {
		width: 64px;
		height: 64px;
		border-radius: 50%;
		display: grid;
		place-items: center;
		font-size: 28px;
		color: white;
		font-weight: 700;
		margin-bottom: 16px;
	}
	.channel-start h3 { margin: 0 0 6px; font-size: 26px; color: #0f0d10; }
	.channel-start p { margin: 0; color: #8a8490; font-size: 15px; }

	.load-older {
		display: block;
		margin: 0 auto 16px;
		font-size: 12px;
		border: 0;
		background: transparent;
		color: #9b1c3a;
		cursor: pointer;
		padding: 4px 8px;
		font-weight: 600;
	}
	.load-older:hover { text-decoration: underline; }

	/* ── Message ── */
	.message {
		position: relative;
		display: grid;
		grid-template-columns: 40px minmax(0, 1fr) auto;
		gap: 0 12px;
		padding: 2px 16px 2px 16px;
		transition: background 0.06s;
	}
	.message:hover {
		background: #f9f8fa;
	}
	.message.grouped {
		padding-top: 1px;
		padding-bottom: 1px;
	}
	.message.deleted .msg-content {
		color: #8a8490;
		font-style: italic;
	}

	/* Avatar */
	.avatar {
		width: 36px;
		height: 36px;
		border-radius: 50%;
		display: grid;
		place-items: center;
		color: white;
		font-size: 13px;
		font-weight: 700;
		margin-top: 3px;
		flex-shrink: 0;
		user-select: none;
	}
	.avatar-gap {
		width: 36px;
		display: flex;
		align-items: center;
		justify-content: flex-end;
	}
	.hover-time {
		font-size: 10px;
		color: #8a8490;
		opacity: 0;
		transition: opacity 0.1s;
		white-space: nowrap;
	}
	.message:hover .hover-time { opacity: 1; }

	/* Body */
	.msg-body {
		min-width: 0;
		padding-bottom: 2px;
	}
	.msg-head {
		display: flex;
		align-items: baseline;
		gap: 8px;
		margin-bottom: 3px;
	}
	.author {
		font-size: 15px;
		font-weight: 700;
		color: #0f0d10;
	}
	.timestamp {
		font-size: 11px;
		color: #8a8490;
	}
	.pin-badge { font-size: 11px; }

	.msg-content {
		margin: 0;
		font-size: 15px;
		line-height: 1.5;
		color: #0f0d10;
		white-space: pre-wrap;
		overflow-wrap: anywhere;
	}

	/* Reply preview */
	.reply-preview {
		display: flex;
		gap: 8px;
		align-items: center;
		margin-bottom: 4px;
		padding-left: 12px;
		border-left: 2px solid #d4d2d8;
		color: #8a8490;
		font-size: 13px;
		overflow: hidden;
	}
	.reply-author { font-weight: 700; color: #9b1c3a; white-space: nowrap; }
	.reply-text {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	/* Reactions */
	.reactions {
		display: flex;
		flex-wrap: wrap;
		gap: 4px;
		margin-top: 4px;
	}
	.reaction {
		display: flex;
		align-items: center;
		gap: 4px;
		padding: 2px 8px;
		border: 1px solid #d4d2d8;
		border-radius: 100px;
		background: #f3f2f5;
		font-size: 13px;
		cursor: pointer;
		transition: background 0.1s, border-color 0.1s;
		min-height: 26px;
	}
	.reaction span { color: #4a4550; font-size: 13px; }
	.reaction:hover { background: #ebebed; border-color: #b4afba; }
	.reaction.reacted { background: #fdf2f5; border-color: #9b1c3a; }
	.reaction.reacted span { color: #9b1c3a; }

	/* Edit form */
	.edit-form {
		margin: 4px 0;
	}
	.edit-form textarea {
		width: 100%;
		border: 1px solid #9b1c3a;
		border-radius: 4px;
		padding: 10px 12px;
		font: inherit;
		font-size: 15px;
		resize: none;
		outline: none;
		background: #fff;
		box-shadow: 0 0 0 2px rgba(155,28,58,0.15);
	}
	.edit-actions {
		display: flex;
		align-items: center;
		gap: 8px;
		margin-top: 6px;
		flex-wrap: wrap;
	}
	.hint { font-size: 11px; color: #8a8490; margin-right: auto; }
	.edit-actions button {
		font-size: 13px;
		padding: 4px 12px;
		border-radius: 6px;
		border: 1px solid #d4d2d8;
		background: #fff;
		cursor: pointer;
		font-weight: 600;
		color: #4a4550;
	}
	.edit-actions button[disabled] { opacity: 0.5; cursor: default; }
	.edit-actions button:first-of-type { background: #9b1c3a; color: white; border-color: #9b1c3a; }
	.edit-actions button:first-of-type:hover:not([disabled]) { background: #7d1630; }

	/* Floating action toolbar */
	.msg-actions {
		display: flex;
		gap: 2px;
		align-items: center;
		opacity: 0;
		pointer-events: none;
		transition: opacity 0.1s;
		position: absolute;
		top: -20px;
		right: 16px;
		background: white;
		border: 1px solid #ebebed;
		border-radius: 8px;
		padding: 3px;
		box-shadow: 0 4px 12px rgba(0,0,0,0.10), 0 0 0 1px rgba(0,0,0,0.06);
		z-index: 2;
	}
	.message:hover .msg-actions {
		opacity: 1;
		pointer-events: all;
	}
	.action-btn {
		display: grid;
		place-items: center;
		width: 28px;
		height: 28px;
		border: 0;
		background: transparent;
		border-radius: 6px;
		font-size: 14px;
		cursor: pointer;
		color: #4a4550;
		transition: background 0.1s;
		padding: 0;
		min-height: 0;
	}
	.action-btn:hover { background: #f3f2f5; }
	.action-btn.danger:hover { background: #fdf2f5; color: #9b1c3a; }

	/* Emoji picker */
	.emoji-picker {
		display: flex;
		gap: 4px;
		padding: 4px 68px;
		animation: fadeIn 0.1s ease;
	}
	.emoji-picker button {
		width: 34px;
		height: 34px;
		border: 1px solid transparent;
		border-radius: 8px;
		background: transparent;
		font-size: 18px;
		cursor: pointer;
		display: grid;
		place-items: center;
		transition: background 0.1s;
		padding: 0;
		min-height: 0;
	}
	.emoji-picker button:hover { background: #f3f2f5; border-color: #d4d2d8; }

	/* Reply bar */
	.reply-bar {
		display: flex;
		align-items: center;
		gap: 8px;
		padding: 7px 16px;
		background: #fdf2f5;
		border-top: 1px solid #f0dde3;
		border-left: 3px solid #9b1c3a;
		font-size: 13px;
		color: #6b6459;
		flex-shrink: 0;
		animation: slideUp 0.1s ease;
	}
	.reply-bar-icon { font-size: 15px; color: #9b1c3a; }
	.reply-bar strong { color: #1a1a1a; }
	.reply-bar button {
		margin-left: auto;
		border: 0;
		background: transparent;
		color: #9b8e84;
		cursor: pointer;
		font-size: 16px;
		line-height: 1;
		padding: 2px 4px;
		border-radius: 4px;
		min-height: 0;
	}
	.reply-bar button:hover { background: #f0dde3; color: #1a1a1a; }

	/* Composer */
	.composer {
		display: flex;
		align-items: flex-end;
		gap: 8px;
		padding: 8px 16px 12px;
		border-top: 1px solid #ebebed;
		flex-shrink: 0;
		background: #fff;
	}
	.composer textarea {
		flex: 1;
		min-width: 0;
		border: 1px solid #e0dde5;
		border-radius: 12px;
		padding: 10px 14px;
		font: inherit;
		font-size: 15px;
		resize: none;
		overflow: hidden;
		line-height: 1.5;
		max-height: 200px;
		transition: border-color 0.15s, background 0.15s, box-shadow 0.15s;
		background: #f3f2f5;
		color: #0f0d10;
	}
	.composer textarea:focus {
		outline: none;
		border-color: #9b1c3a;
		background: #fff;
		box-shadow: 0 0 0 2px rgba(155,28,58,0.15);
	}
	.composer textarea::placeholder { color: #8a8490; }
	.composer.archived textarea {
		background: #f9f8fa;
		color: #8a8490;
	}
	.send-btn {
		width: 36px;
		height: 36px;
		border-radius: 50%;
		border: 0;
		background: #9b1c3a;
		color: white;
		cursor: pointer;
		display: grid;
		place-items: center;
		flex-shrink: 0;
		transition: background 0.1s, transform 0.1s;
		padding: 0;
	}
	.send-btn:hover:not([disabled]) { background: #7d1630; transform: scale(1.05); }
	.send-btn[disabled] { background: #d4d2d8; color: #8a8490; cursor: default; }

	.error {
		padding: 8px 16px;
		font-size: 13px;
		color: #9b1c3a;
		background: #fdf2f5;
		border-bottom: 1px solid #f0dde3;
		flex-shrink: 0;
	}

	/* Animations */
	@keyframes slideDown {
		from { opacity: 0; transform: translateY(-6px); }
		to { opacity: 1; transform: translateY(0); }
	}
	@keyframes slideUp {
		from { opacity: 0; transform: translateY(4px); }
		to { opacity: 1; transform: translateY(0); }
	}
	@keyframes fadeIn {
		from { opacity: 0; }
		to { opacity: 1; }
	}

	/* Focus styles */
	button:focus-visible, textarea:focus-visible, input:focus-visible {
		outline: 2px solid #9b1c3a;
		outline-offset: 2px;
	}
</style>
