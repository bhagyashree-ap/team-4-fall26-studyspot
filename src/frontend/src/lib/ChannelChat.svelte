<script lang="ts">
	import { chatControls } from '$lib/chatControls';
	import { Textarea } from '$lib/components/ui/textarea';
	import SearchMessages from './SearchMessages.svelte';
	import MessageLink from './MessageLink.svelte';
	import LinkedMessage from './LinkedMessage.svelte';
	import Ballot from './Ballot.svelte';
	import ComposerTools from './ComposerTools.svelte';
	import Send from '@lucide/svelte/icons/send';
	import Pin from '@lucide/svelte/icons/pin';
	import MessageSquare from '@lucide/svelte/icons/message-square';
	import Pencil from '@lucide/svelte/icons/pencil';
	import Trash2 from '@lucide/svelte/icons/trash-2';
	import Reply from '@lucide/svelte/icons/reply';
	import Mail from '@lucide/svelte/icons/mail';
	import CheckCheck from '@lucide/svelte/icons/check-check';
	import Link2 from '@lucide/svelte/icons/link-2';
	import Search from '@lucide/svelte/icons/search';
	import Hash from '@lucide/svelte/icons/hash';
	import { pollMessages, mergeMessages } from './history';
	import EmojiPicker from './EmojiPicker.svelte';
	import ChatThread from './ChatThread.svelte';
	import Attachment from './Attachment.svelte';
	import { composeMessage } from './communities';
	import MessageBody from './MessageBody.svelte';
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
		names = [],
		onShare,
		onDirectMessage
	}: {
		communityId: number;
		channel: Channel;
		names?: string[];
		role: string;
		onShare: () => void;
		onDirectMessage: (conversation: DirectConversation) => void;
	} = $props();

	let messages = $state<Message[]>([]);
	let hasOlder = $state(false);
	let content = $state('');
	let replyTo = $state<Message | null>(null);
	let editingId = $state<number | null>(null);
	let draft = $state('');
	let showSearch = $state(false);

	let results = $state<Pick<Message, 'id' | 'author_name' | 'created_at' | 'content'>[] | null>(
		null
	);
	let showPinsPanel = $state(false);
	let pins = $state<Message[] | null>(null);
	let error = $state('');
	let files = $state<FileList>();
	let thread = $state<{ id: number; content: string } | null>(null);
	let lastRead = $state(0);
	async function mark(unread_from?: number) {
		try {
			const result = await communityRequest<{ last_read: number }>(
				base() + '/read',
				'PUT',
				unread_from ? { unread_from } : {}
			);
			lastRead = result.last_read;
		} catch (e) {
			error = problem(e);
		}
	}
	let presence = $state<ComposerTools>();
	let sending = $state(false);
	let cursor: number | null = null,
		refreshCount = 0;
	let polling = false;
	let generation = 0;
	let messageList = $state<HTMLDivElement>();
	let composeEl = $state<HTMLTextAreaElement>();

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

	const palette = ['#5865b9', '#976689', '#377f73', '#95634d', '#79659b', '#43728b', '#8c6441'];
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
			cursor = page.items.at(-1)?.id ?? 0;
			hasOlder = page.has_more;
			error = '';
			await scrollToBottom();
		} catch (cause) {
			if (current === generation) error = problem(cause);
		}
	}

	async function refresh() {
		if (polling || document.hidden || cursor === null) return;
		polling = true;
		const current = generation;
		try {
			const visible = ++refreshCount % 3 === 0 ? messages.slice(-250).map((m) => m.id) : [];
			const page = await pollMessages<Message>(base() + '/messages', cursor, visible);
			if (current !== generation) return;
			const previous = cursor;
			cursor = page.after;
			const merged = mergeMessages(messages, page.updates);
			hasOlder ||= merged.length > 250;
			messages = merged.slice(-250);
			if (
				cursor > previous &&
				messageList &&
				messageList.scrollHeight - messageList.scrollTop - messageList.clientHeight < 160
			)
				await scrollToBottom();
			if (page.more)
				window.setTimeout(() => {
					if (current === generation) void refresh();
				}, 0);
		} catch (e) {
			if (current === generation) error = problem(e);
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
		if ((!content.trim() && !files?.length) || sending) return;
		sending = true;
		const body = { content: content.trim(), ...(replyTo ? { reply_to: replyTo.id } : {}) };
		try {
			const message = await communityRequest<Message>(
				`${base()}/messages`,
				'POST',
				composeMessage(body, files?.[0])
			);
			messages = mergeMessages(messages, [message]);
			files = new DataTransfer().files;
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
						? {
								...item,
								content: '',
								deleted_at: new Date().toISOString(),
								reactions: [],
								pinned_at: null
							}
						: item
				);
			} else {
				messages = messages.map((item) => (item.id === changed.id ? changed : item));
			}
			if (method === 'PATCH') editingId = null;
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
		<Hash size={22} class="channel-hash" />
		<strong class="channel-title">{channel.name}</strong>
		{#if channel.slowmode_seconds}<span>Slowmode · {channel.slowmode_seconds}s</span>{/if}
		{#if channel.read_only}<span>Read-only</span>{/if}
		{#if channel.archived}<span class="archived-badge">Archived</span>{/if}
		{#if channel.topic}<span class="header-topic">{channel.topic}</span>{/if}
		<div class="header-actions">
			<button
				class="icon-btn {chatControls.icon}"
				title="Copy channel link"
				aria-label="Copy channel link"
				onclick={onShare}><Link2 size={18} /></button
			>
			<button
				class="icon-btn {chatControls.icon}"
				class:active={showSearch}
				aria-label="Search messages"
				title="Search"
				onclick={() => {
					showSearch = !showSearch;
					if (!showSearch) {
						results = null;
					}
					pins = null;
					showPinsPanel = false;
				}}
			>
				<Search size={18} />
			</button>
			<button
				class="icon-btn {chatControls.icon}"
				class:active={showPinsPanel}
				aria-label="Pinned messages"
				title="Pins"
				onclick={() => {
					void loadPins();
					showSearch = false;
				}}
			>
				<Pin size={18} />
			</button>
		</div>
	</div>

	{#if showSearch}
		<SearchMessages
			url={`/communities/${communityId}/messages/search`}
			onresults={(items) => {
				results = items;
				pins = null;
			}}
			onerror={(s) => (error = s)}
		/>
	{/if}

	{#if thread}{#key thread.id}<ChatThread
				url={base() + '/messages'}
				root={thread}
				onclose={() => (thread = null)}
			/>{/key}{/if}
	<LinkedMessage loaded={messages} url={base() + '/messages'} />
	{#if error}<p class="error" role="alert">{error}</p>{/if}

	{#if results !== null || (pins !== null && showPinsPanel)}
		<div class="overlay-panel">
			<div class="overlay-header">
				<h4>{results !== null ? 'Search results' : 'Pinned messages'}</h4>
				<button class="icon-btn {chatControls.icon}" onclick={closeOverlay} aria-label="Close"
					>✕</button
				>
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
				<button class="load-older {chatControls.ghost}" onclick={() => void older()}
					>Load older messages</button
				>
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
				{#if message.id > lastRead && messages.find((m) => m.id > lastRead)?.id === message.id}<div
						class="unread-divider"
					>
						Unread messages
					</div>{/if}
				<article
					class="message"
					class:grouped={!header}
					class:deleted={!!message.deleted_at}
					id={`message-${message.id}`}
				>
					{#if header}
						<div
							class="avatar"
							style="background:{avatarColor(message.author_name)}"
							aria-hidden="true"
						>
							{initials(message.author_name)}
						</div>
					{:else}
						<div class="avatar-gap" aria-hidden="true">
							<time class="hover-time"
								>{new Date(message.created_at).toLocaleTimeString([], {
									hour: 'numeric',
									minute: '2-digit'
								})}</time
							>
						</div>
					{/if}
					<div class="msg-body">
						{#if header}
							<div class="msg-head">
								<strong class="author">{message.author_name}</strong>
								<time class="timestamp" datetime={message.created_at}
									>{formatTime(message.created_at)}</time
								>
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
								onsubmit={(e) => {
									e.preventDefault();
									void change(message, 'PATCH', '', { content: draft });
								}}
							>
								<Textarea
									aria-label="Edit message"
									maxlength={2000}
									bind:value={draft}
									rows={2}
									onkeydown={(e) => {
										if (e.key === 'Enter' && !e.shiftKey) {
											e.preventDefault();
											void change(message, 'PATCH', '', { content: draft });
										}
										if (e.key === 'Escape') editingId = null;
									}}
								></Textarea>
								<div class="edit-actions">
									<span class="hint">Enter to save · Escape to cancel</span>
									<button class={chatControls.ghost} disabled={!draft.trim()}>Save</button>
									<button
										class={chatControls.ghost}
										type="button"
										onclick={() => (editingId = null)}>Cancel</button
									>
								</div>
							</form>
						{:else}
							{#if message.deleted_at}This message was deleted.{:else}{#if message.poll}<Ballot
										poll={message.poll}
										url={base() + '/messages' + '/' + message.id + '/vote'}
										onvote={(poll) =>
											(messages = messages.map((m) => (m.id === message.id ? { ...m, poll } : m)))}
									/>{/if}{#if message.file_name}<Attachment
										url={base() + '/messages/' + message.id}
										name={message.file_name}
									/>{/if}<MessageBody content={message.content} />{#if message.edited_at}<small
										>(edited)</small
									>{/if}{/if}
						{/if}
						{#if message.reactions.length}
							<div class="reactions">
								{#each message.reactions as reaction (reaction.emoji)}
									<button
										class="reaction {chatControls.ghost}"
										class:reacted={reaction.me}
										onclick={() =>
											void change(
												message,
												reaction.me ? 'DELETE' : 'POST',
												`/reactions${reaction.me ? `/${encodeURIComponent(reaction.emoji)}` : ''}`,
												reaction.me ? undefined : { emoji: reaction.emoji }
											)}>{reaction.emoji} <span>{reaction.count}</span></button
									>
								{/each}
							</div>
						{/if}
					</div>

					{#if !message.deleted_at}
						<div class="msg-actions" role="toolbar" aria-label="Message actions">
							<EmojiPicker
								reaction
								onpick={(emoji) => void change(message, 'POST', '/reactions', { emoji })}
							/><button
								class={chatControls.icon}
								onclick={() => (thread = message)}
								title="Open thread"
								aria-label="Open thread"><MessageSquare size={16} /></button
							><button
								class={chatControls.icon}
								onclick={() => void mark(message.id)}
								title="Mark unread"
								aria-label="Mark unread"><CheckCheck size={16} /></button
							><MessageLink id={message.id} />
							<button
								class="action-btn {chatControls.icon}"
								title="Reply"
								onclick={() => (replyTo = message)}><Reply size={16} /></button
							>
							{#if !message.mine}
								<button
									class="action-btn {chatControls.icon}"
									title="Direct message"
									onclick={() => void startDM(message)}><Mail size={16} /></button
								>
							{/if}
							{#if message.mine}
								<button
									class="action-btn {chatControls.icon}"
									title="Edit message"
									onclick={() => {
										editingId = message.id;
										draft = message.content;
									}}><Pencil size={16} /></button
								>
							{/if}
							{#if role === 'owner' || role === 'moderator'}
								<button
									class="action-btn {chatControls.icon}"
									title={message.pinned_at ? 'Unpin' : 'Pin message'}
									onclick={() =>
										void change(message, message.pinned_at ? 'DELETE' : 'POST', '/pin')}
									><Pin size={16} /></button
								>
							{/if}
							{#if message.can_delete}
								<button
									class="action-btn danger {chatControls.danger}"
									title="Delete message"
									onclick={() => {
										if (confirm('Delete this message?')) void change(message, 'DELETE');
									}}><Trash2 size={16} /></button
								>
							{/if}
						</div>
					{/if}
				</article>
			{/each}
		</div>

		{#if replyTo}
			<div class="reply-bar">
				<span class="reply-bar-icon">↩</span>
				<span
					>Replying to <strong>{replyTo.author_name}</strong> — {replyTo.content.slice(
						0,
						60
					)}{replyTo.content.length > 60 ? '…' : ''}</span
				>
				<button class={chatControls.icon} onclick={() => (replyTo = null)} aria-label="Cancel reply"
					>✕</button
				>
			</div>
		{/if}

		{#if files?.length}<p class="attachment-chip">
				{files[0].name}
				<button
					class={chatControls.icon}
					type="button"
					aria-label="Remove attachment"
					onclick={() => (files = new DataTransfer().files)}>×</button
				>
			</p>{/if}
		<div class="composer" class:archived={channel.archived}>
			<ComposerTools
				room={base()}
				{names}
				groups={role === 'owner' || role === 'moderator'}
				bind:files
				bind:this={presence}
				onread={(id) => (lastRead = id)}
				onmention={(v) => (content += (content ? ' ' : '') + v + ' ')}
				onmark={() => void mark()}
				onsent={() => void refresh()}
			/>
			<Textarea
				bind:ref={composeEl}
				aria-label={channel.archived ? 'Channel is archived' : `Message #${channel.name}`}
				placeholder={channel.archived ? 'This channel is archived.' : `Message #${channel.name}`}
				maxlength={2000}
				rows={1}
				bind:value={content}
				disabled={channel.archived || (channel.read_only && role === 'member')}
				onkeydown={handleCompose}
				oninput={() => {
					resizeCompose();
					presence?.typing();
				}}
			></Textarea>
			<EmojiPicker onpick={(v) => (content += v)} /><button
				class="send-btn {chatControls.icon}"
				disabled={channel.archived ||
					(channel.read_only && role === 'member') ||
					sending ||
					(!content.trim() && !files?.length)}
				onclick={() => void send()}
				aria-label="Send message"
			>
				<Send size={19} />
			</button>
		</div>
	{/if}
</div>

<style>
	.unread-divider {
		border-top: 1px solid var(--accent);
		color: var(--accent);
		font-size: 0.8rem;
		text-align: center;
	}
	.chat {
		position: relative;
	}
	.chat {
		display: flex;
		flex-direction: column;
		flex: 1;
		min-height: 0;
		background: var(--panel);
	}

	/* ── Header ── */
	.chat-header {
		display: flex;
		align-items: center;
		gap: 8px;
		height: 48px;
		padding: 0 16px;
		border-bottom: 1px solid var(--line);
		flex-shrink: 0;
		background: var(--panel);
	}
	.channel-title {
		font-size: 15px;
		font-weight: 700;
		color: var(--ink);
	}
	.archived-badge {
		font-size: 11px;
		background: var(--well);
		color: var(--muted);
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
		color: var(--muted);
		cursor: pointer;
		transition:
			background 0.12s,
			color 0.12s;
		padding: 0;
		min-height: 0;
		font-size: 14px;
	}
	.icon-btn:hover {
		background: var(--well);
		color: var(--ink);
	}
	.icon-btn.active {
		background: var(--selected);
		color: var(--accent);
	}

	/* ── Search bar ── */

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
		border-bottom: 1px solid var(--line);
		flex-shrink: 0;
	}
	.overlay-header h4 {
		margin: 0;
		font-size: 14px;
		font-weight: 700;
		color: var(--ink);
	}
	.overlay-list {
		flex: 1;
		min-height: 0;
		overflow-y: auto;
		padding: 8px 20px;
	}
	.overlay-message {
		padding: 10px 0;
		border-bottom: 1px solid var(--well);
	}
	.overlay-meta {
		display: flex;
		gap: 10px;
		align-items: baseline;
		margin-bottom: 4px;
	}
	.overlay-meta strong {
		font-size: 14px;
		color: var(--ink);
	}
	.overlay-meta time {
		font-size: 11px;
		color: var(--muted);
	}
	.overlay-message p {
		margin: 0;
		font-size: 14px;
		color: var(--muted);
	}
	.empty {
		color: var(--muted);
		font-size: 14px;
	}

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
		color: var(--muted);
		font-size: 12px;
		font-weight: 600;
	}
	.date-sep::before,
	.date-sep::after {
		content: '';
		flex: 1;
		height: 1px;
		background: var(--line);
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
	.channel-start h3 {
		margin: 0 0 6px;
		font-size: 26px;
		color: var(--ink);
	}
	.channel-start p {
		margin: 0;
		color: var(--muted);
		font-size: 15px;
	}

	.load-older {
		display: block;
		margin: 0 auto 16px;
		font-size: 12px;
		border: 0;
		background: transparent;
		color: var(--accent);
		cursor: pointer;
		padding: 4px 8px;
		font-weight: 600;
	}
	.load-older:hover {
		text-decoration: underline;
	}

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
		background: var(--hover);
	}
	.message.grouped {
		padding-top: 1px;
		padding-bottom: 1px;
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
		color: var(--muted);
		opacity: 0;
		transition: opacity 0.1s;
		white-space: nowrap;
	}
	.message:hover .hover-time {
		opacity: 1;
	}

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
		color: var(--ink);
	}
	.timestamp {
		font-size: 11px;
		color: var(--muted);
	}
	.pin-badge {
		font-size: 11px;
	}

	/* Reply preview */
	.reply-preview {
		display: flex;
		gap: 8px;
		align-items: center;
		margin-bottom: 4px;
		padding-left: 12px;
		border-left: 2px solid var(--line);
		color: var(--muted);
		font-size: 13px;
		overflow: hidden;
	}
	.reply-author {
		font-weight: 700;
		color: var(--accent);
		white-space: nowrap;
	}
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
		border: 1px solid var(--line);
		border-radius: 100px;
		background: var(--well);
		font-size: 13px;
		cursor: pointer;
		transition:
			background 0.1s,
			border-color 0.1s;
		min-height: 26px;
	}
	.reaction span {
		color: var(--muted);
		font-size: 13px;
	}
	.reaction:hover {
		background: var(--line);
		border-color: var(--muted);
	}
	.reaction.reacted {
		background: var(--selected);
		border-color: var(--accent);
	}
	.reaction.reacted span {
		color: var(--accent);
	}

	/* Edit form */
	.edit-form {
		margin: 4px 0;
	}
	.edit-form :global(textarea) {
		width: 100%;
		border: 1px solid var(--accent);
		border-radius: 4px;
		padding: 10px 12px;
		font: inherit;
		font-size: 15px;
		resize: none;
		outline: none;
		background: var(--panel);
		box-shadow: 0 0 0 2px var(--selected);
	}
	.edit-actions {
		display: flex;
		align-items: center;
		gap: 8px;
		margin-top: 6px;
		flex-wrap: wrap;
	}
	.hint {
		font-size: 11px;
		color: var(--muted);
		margin-right: auto;
	}
	.edit-actions button {
		font-size: 13px;
		padding: 4px 12px;
		border-radius: 6px;
		border: 1px solid var(--line);
		background: var(--panel);
		cursor: pointer;
		font-weight: 600;
		color: var(--muted);
	}
	.edit-actions button[disabled] {
		opacity: 0.5;
		cursor: default;
	}
	.edit-actions button:first-of-type {
		background: var(--accent);
		color: white;
		border-color: var(--accent);
	}
	.edit-actions button:first-of-type:hover:not([disabled]) {
		background: var(--accent-h);
	}

	@media (hover: none) {
		.message .msg-actions {
			position: static;
			grid-column: 2/-1;
			opacity: 1;
			pointer-events: auto;
			flex-wrap: wrap;
		}
	}
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
		background: var(--panel);
		border: 1px solid var(--line);
		border-radius: 8px;
		padding: 3px;
		box-shadow:
			0 4px 12px rgba(0, 0, 0, 0.1),
			0 0 0 1px rgba(0, 0, 0, 0.06);
		z-index: 2;
	}
	.message:focus-within .msg-actions,
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
		color: var(--muted);
		transition: background 0.1s;
		padding: 0;
		min-height: 0;
	}
	.action-btn:hover {
		background: var(--well);
	}
	.action-btn.danger:hover {
		background: var(--selected);
		color: var(--accent);
	}

	/* Emoji picker */

	/* Reply bar */
	.reply-bar {
		display: flex;
		align-items: center;
		gap: 8px;
		padding: 7px 16px;
		background: var(--selected);
		border-top: 1px solid var(--selected);
		border-left: 3px solid var(--accent);
		font-size: 13px;
		color: var(--muted);
		flex-shrink: 0;
		animation: slideUp 0.1s ease;
	}
	.reply-bar-icon {
		font-size: 15px;
		color: var(--accent);
	}
	.reply-bar strong {
		color: var(--ink);
	}
	.reply-bar button {
		margin-left: auto;
		border: 0;
		background: transparent;
		color: var(--muted);
		cursor: pointer;
		font-size: 16px;
		line-height: 1;
		padding: 2px 4px;
		border-radius: 4px;
		min-height: 0;
	}
	.reply-bar button:hover {
		background: var(--selected);
		color: var(--ink);
	}

	/* Composer */
	.composer {
		display: flex;
		align-items: flex-end;
		gap: 8px;
		padding: 8px 16px 12px;
		border-top: 1px solid var(--line);
		flex-shrink: 0;
		background: var(--panel);
	}
	.composer :global(textarea) {
		flex: 1;
		min-width: 0;
		border: 1px solid var(--line);
		border-radius: 12px;
		padding: 10px 14px;
		font: inherit;
		font-size: 15px;
		resize: none;
		overflow: hidden;
		line-height: 1.5;
		max-height: 200px;
		transition:
			border-color 0.15s,
			background 0.15s,
			box-shadow 0.15s;
		background: var(--well);
		color: var(--ink);
	}
	.composer :global(textarea:focus) {
		outline: none;
		border-color: var(--accent);
		background: var(--panel);
		box-shadow: 0 0 0 2px var(--selected);
	}
	.composer :global(textarea::placeholder) {
		color: var(--muted);
	}
	.composer.archived :global(textarea) {
		background: var(--hover);
		color: var(--muted);
	}
	.send-btn {
		width: 36px;
		height: 36px;
		border-radius: 50%;
		border: 0;
		background: var(--accent);
		color: white;
		cursor: pointer;
		display: grid;
		place-items: center;
		flex-shrink: 0;
		transition:
			background 0.1s,
			transform 0.1s;
		padding: 0;
	}
	.send-btn:hover:not([disabled]) {
		background: var(--accent-h);
		transform: scale(1.05);
	}
	.send-btn[disabled] {
		background: var(--line);
		color: var(--muted);
		cursor: default;
	}

	.error {
		padding: 8px 16px;
		font-size: 13px;
		color: var(--accent);
		background: var(--selected);
		border-bottom: 1px solid var(--selected);
		flex-shrink: 0;
	}

	/* Animations */
	@keyframes slideDown {
		from {
			opacity: 0;
			transform: translateY(-6px);
		}
		to {
			opacity: 1;
			transform: translateY(0);
		}
	}
	@keyframes slideUp {
		from {
			opacity: 0;
			transform: translateY(4px);
		}
		to {
			opacity: 1;
			transform: translateY(0);
		}
	}
	@keyframes fadeIn {
		from {
			opacity: 0;
		}
		to {
			opacity: 1;
		}
	}

	/* Focus styles */
	button:focus-visible,
	.chat :global(textarea:focus-visible) {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}
</style>
