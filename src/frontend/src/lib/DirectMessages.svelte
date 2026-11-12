<script lang="ts">
	import { chatControls } from '$lib/chatControls';
	import { Input } from '$lib/components/ui/input';
	import Settings from '@lucide/svelte/icons/settings';
	import Pin from '@lucide/svelte/icons/pin';
	import Search from '@lucide/svelte/icons/search';
	import X from '@lucide/svelte/icons/x';
	import Presence from './Presence.svelte';
	import SearchMessages from './SearchMessages.svelte';
	import MessageActions from './MessageActions.svelte';
	import { tick } from 'svelte';
	import LinkedMessage from './LinkedMessage.svelte';
	import Ballot from './Ballot.svelte';
	import ComposerTools from './ComposerTools.svelte';
	import Send from '@lucide/svelte/icons/send';
	import { pollMessages, mergeMessages } from './history';
	import EmojiPicker from './EmojiPicker.svelte';
	import ChatThread from './ChatThread.svelte';
	import Attachment from './Attachment.svelte';
	import { composeMessage } from './communities';
	import MessageBody from './MessageBody.svelte';
	import { communityRequest, type DirectConversation, type DirectMessage } from './communities';

	let {
		conversation,
		presentation = 'page',
		onread
	}: {
		conversation: DirectConversation;
		presentation?: 'page' | 'inbox';
		onread?: () => void;
	} = $props();
	let messages = $state<DirectMessage[]>([]);
	let scroller: HTMLDivElement;
	let following = true;
	let pointerSend = false;
	let arriving = $state(new Set<number>());
	let composerInput = $state<HTMLInputElement>();
	const timeLabel = (value: string) =>
		new Date(value).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
	const dateLabel = (value: string) =>
		new Date(value).toLocaleDateString([], { month: 'long', day: 'numeric' });
	function grouped(previous: DirectMessage | undefined, message: DirectMessage | undefined) {
		return (
			previous &&
			message &&
			dateLabel(previous.created_at) === dateLabel(message.created_at) &&
			previous.mine === message.mine &&
			!previous.deleted_at &&
			!message.deleted_at &&
			new Date(message.created_at).getTime() - new Date(previous.created_at).getTime() < 300000
		);
	}
	function bottom() {
		scroller?.scrollTo({ top: scroller.scrollHeight, behavior: 'instant' });
	}
	function action(
		message: DirectMessage,
		action: 'reply' | 'pin' | 'thread' | 'unread' | 'edit' | 'delete'
	) {
		switch (action) {
			case 'reply':
				replyTo = message;
				composerInput?.focus();
				break;
			case 'pin':
				void pin(message);
				break;
			case 'thread':
				thread = message;
				break;
			case 'unread':
				void mark(message.id);
				break;
			case 'edit':
				editingId = message.id;
				draft = message.content;
				void tick().then(() =>
					scroller.querySelector<HTMLInputElement>('[aria-label="Edit direct message"]')?.focus()
				);
				break;
			case 'delete':
				if (confirm('Delete this message?')) void change(message, 'DELETE');
				break;
		}
	}
	async function react(item: DirectMessage, emoji: string) {
		try {
			const updated = await communityRequest<DirectMessage>(
				base() + '/' + item.id + '/reactions',
				'PUT',
				{ emoji, active: !item.reactions?.find((r) => r.emoji === emoji)?.me }
			);
			messages = messages.map((m) => (m.id === item.id ? updated : m));
		} catch (e) {
			error = problem(e);
		}
	}
	let pins = $state<DirectMessage[]>([]);
	async function showPins() {
		try {
			pins = (await communityRequest<{ items: DirectMessage[] }>(`/dms/${conversation.id}/pins`))
				.items;
		} catch (e) {
			error = problem(e);
		}
	}
	async function pin(item: DirectMessage) {
		try {
			const updated = await communityRequest<DirectMessage>(
				base() + '/' + item.id + '/pin',
				'PUT',
				{ pinned: !item.pinned_at }
			);
			messages = messages.map((m) => (m.id === item.id ? updated : m));
			await showPins();
		} catch (e) {
			error = problem(e);
		}
	}
	let matches = $state<Pick<DirectMessage, 'id' | 'author_name' | 'content'>[]>([]);
	let hasOlder = $state(false);
	let content = $state('');
	let replyTo = $state<DirectMessage | null>(null);
	let editingId = $state<number | null>(null);
	let draft = $state('');
	let error = $state('');
	let files = $state<FileList>();
	let thread = $state<{ id: number; content: string } | null>(null);
	let lastRead = $state(0);
	let autoRead = true;
	let marking = false;
	async function mark(unread_from?: number) {
		if (unread_from) autoRead = false;
		try {
			const result = await communityRequest<{ last_read: number }>(
				`/dms/${conversation.id}` + '/read',
				'PUT',
				unread_from ? { unread_from } : {}
			);
			lastRead = result.last_read;
			onread?.();
		} catch (e) {
			error = problem(e);
		}
	}
	async function readVisible() {
		const last = messages.at(-1)?.id;
		if (!last || !autoRead || marking || document.hidden || !following || last <= lastRead) return;
		marking = true;
		try {
			const result = await communityRequest<{ last_read: number }>(
				`/dms/${conversation.id}/read`,
				'PUT',
				{ read_through: last }
			);
			lastRead = result.last_read;
			onread?.();
		} catch (cause) {
			error = problem(cause);
		} finally {
			marking = false;
		}
	}

	let presence = $state<Presence>();
	let typingNames = $state<string[]>([]);
	let panel = $state<'pins' | 'search' | 'settings' | null>(null);
	let searched = $state(false);
	let sending = $state(false);
	let cursor: number | null = null,
		refreshCount = 0;
	let polling = false;
	let generation = 0;
	const base = () => `/dms/${conversation.id}/messages`;
	const problem = (cause: unknown) =>
		cause instanceof Error ? cause.message : 'Something went wrong.';

	async function load() {
		const current = ++generation;
		try {
			const page = await communityRequest<{ items: DirectMessage[]; has_more: boolean }>(base());
			if (current !== generation) return;
			messages = page.items;
			cursor = page.items.at(-1)?.id ?? 0;
			hasOlder = page.has_more;
			error = '';
			await tick();
			if (current === generation && !location.hash) {
				bottom();
				void readVisible();
			}
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
			const page = await pollMessages<DirectMessage>(base(), cursor, visible);
			if (current !== generation) return;

			cursor = page.after;
			const known = new Set(messages.map((item) => item.id));
			arriving = new Set(
				page.updates.filter((item) => !known.has(item.id) && !item.mine).map((item) => item.id)
			);
			const shouldFollow = following;
			const merged = mergeMessages(messages, page.updates);
			hasOlder ||= merged.length > 250;
			messages = merged.slice(-250);
			await tick();
			if (current === generation && shouldFollow) {
				bottom();
				void readVisible();
			}

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
		try {
			const oldHeight = scroller.scrollHeight;
			const page = await communityRequest<{ items: DirectMessage[]; has_more: boolean }>(
				`${base()}?before=${messages[0].id}`
			);
			messages = [...page.items, ...messages];
			hasOlder = page.has_more;
			await tick();
			scroller.scrollTop += scroller.scrollHeight - oldHeight;
		} catch (cause) {
			error = problem(cause);
		}
	}

	async function send() {
		if ((!content.trim() && !files?.length) || sending) return;
		sending = true;
		const animate = pointerSend;
		pointerSend = false;
		try {
			const sent = await communityRequest<DirectMessage>(
				base(),
				'POST',
				composeMessage(
					{
						content,
						...(replyTo ? { reply_to: replyTo.id } : {})
					},
					files?.[0]
				)
			);
			arriving = new Set(animate ? [sent.id] : []);
			messages = mergeMessages(messages, [sent]);
			files = new DataTransfer().files;
			content = '';
			replyTo = null;
			error = '';
			await tick();
			bottom();
			void readVisible();
		} catch (cause) {
			error = problem(cause);
		} finally {
			sending = false;
		}
	}

	async function change(message: DirectMessage, method: 'PATCH' | 'DELETE') {
		try {
			const updated = await communityRequest<DirectMessage>(
				`${base()}/${message.id}`,
				method,
				method === 'PATCH' ? { content: draft } : undefined
			);
			messages = messages.map((item) =>
				item.id === message.id
					? method === 'PATCH'
						? updated
						: { ...item, content: '', deleted_at: new Date().toISOString() }
					: item
			);
			editingId = null;
			error = '';
		} catch (cause) {
			error = problem(cause);
		}
	}

	$effect(() => {
		void conversation.id;
		messages = [];
		hasOlder = false;
		void load();
		const timer = window.setInterval(() => void refresh(), 3000);
		return () => {
			window.clearInterval(timer);
			generation++;
		};
	});
</script>

<div class="dm" class:inbox-conversation={presentation === 'inbox'}>
	<header class="dm-toolbar">
		<span class="recipient-avatar" aria-hidden="true"
			>{conversation.other_name
				.trim()
				.split(/\s+/)
				.slice(0, 2)
				.map((part) => part[0])
				.join('')}</span
		>
		<h2>{conversation.other_name}</h2>
		<button
			class="chat-icon {chatControls.icon}"
			title="Pinned messages"
			aria-label="Pinned messages"
			aria-expanded={panel === 'pins'}
			onclick={() => {
				panel = panel === 'pins' ? null : 'pins';
				if (panel) void showPins();
			}}><Pin size={18} /></button
		>
		<button
			class="chat-icon {chatControls.icon}"
			title="Search conversation"
			aria-label="Search conversation"
			aria-expanded={panel === 'search'}
			onclick={() => (panel = panel === 'search' ? null : 'search')}><Search size={18} /></button
		>
		<button
			class="chat-icon {chatControls.icon}"
			title="Conversation settings"
			aria-label="Conversation settings"
			aria-expanded={panel === 'settings'}
			onclick={() => (panel = panel === 'settings' ? null : 'settings')}
			><Settings size={18} /></button
		>
	</header>
	<section class="dm-panel" hidden={panel !== 'settings'}>
		<h3>Conversation settings</h3>
		<Presence
			expanded
			url={`/dms/${conversation.id}/presence`}
			bind:this={presence}
			onread={(id) => {
				if (autoRead) lastRead = Math.max(lastRead, id);
			}}
			ontyping={(names) => (typingNames = names)}
		/>
	</section>
	{#if panel === 'pins'}<section class="dm-panel">
			<h3>Pinned messages</h3>
			{#each pins as item (item.id)}<p>
					<strong>{item.author_name}</strong> · {item.content}
				</p>{:else}<p>No pinned messages yet.</p>{/each}
		</section>
	{:else if panel === 'search'}<section class="dm-panel">
			<h3>Search conversation</h3>
			<SearchMessages
				url={base() + '/search'}
				onresults={(items) => {
					matches = items;
					searched = true;
				}}
				onerror={(s) => (error = s)}
			/>{#each matches as item (item.id)}<p>
					<strong>{item.author_name}</strong> · {item.content}
				</p>{:else}{#if searched}<p>No matching messages.</p>{/if}{/each}
		</section>{/if}
	{#if thread}{#key thread.id}<ChatThread
				url={base()}
				root={thread}
				onclose={() => (thread = null)}
			/>{/key}{/if}
	<LinkedMessage loaded={messages} url={base()} />
	{#if error}<p class="error" role="alert">{error}</p>{/if}
	<div
		class="messages"
		bind:this={scroller}
		role="log"
		aria-label={'Messages with ' + conversation.other_name}
		aria-live="polite"
		onscroll={() => {
			following = scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight < 80;
			if (following) void readVisible();
		}}
	>
		{#if hasOlder}<button class="older {chatControls.ghost}" onclick={() => void older()}
				>Load older messages</button
			>{/if}
		{#each messages as message, index (message.id)}
			{#if index === 0 || dateLabel(messages[index - 1].created_at) !== dateLabel(message.created_at)}<div
					class="day-divider"
				>
					{dateLabel(message.created_at)}
				</div>{/if}
			{#if message.id > lastRead && messages.find((m) => m.id > lastRead)?.id === message.id}<div
					class="unread-divider"
				>
					New messages
				</div>{/if}
			<article
				id={`message-${message.id}`}
				class="message-row"
				class:mine={message.mine}
				class:grouped={!!grouped(messages[index - 1], message)}
				aria-label={'Message from ' + (message.mine ? 'you' : message.author_name)}
				oncontextmenu={(event) => {
					if (message.deleted_at || (event.target as HTMLElement).closest('.message-actions'))
						return;
					event.preventDefault();
					const trigger = event.currentTarget.querySelector<HTMLButtonElement>('.action-trigger');
					if (!trigger) return;
					trigger.dataset.contextX = String(event.clientX);
					trigger.dataset.contextY = String(event.clientY);
					trigger.click();
				}}
			>
				{#if conversation.kind === 'group' && !message.mine && !grouped(messages[index - 1], message)}<span
						class="sender-name">{message.author_name}</span
					>{/if}
				<div class="message-line">
					<div
						class="bubble"
						class:arriving={arriving.has(message.id)}
						class:deleted={!!message.deleted_at}
					>
						{#if message.reply_to}<div class="reply-preview">
								<span
									>Replying to {messages.find((item) => item.id === message.reply_to)
										?.author_name ?? 'an earlier message'}</span
								>
								<p>
									{messages.find((item) => item.id === message.reply_to)?.content ??
										'Earlier message'}
								</p>
							</div>{/if}
						{#if editingId === message.id}
							<form
								class="edit"
								onsubmit={(event) => {
									event.preventDefault();
									void change(message, 'PATCH');
								}}
							>
								<Input aria-label="Edit direct message" maxlength={2000} bind:value={draft} />
								<div>
									<button class={chatControls.ghost} disabled={!draft.trim()}>Save</button><button
										class={chatControls.ghost}
										type="button"
										onclick={() => (editingId = null)}>Cancel</button
									>
								</div>
							</form>
						{:else if message.deleted_at}<span>Message deleted</span>
						{:else}
							{#if message.poll}<div class="rich-content">
									<Ballot
										poll={message.poll}
										url={base() + '/' + message.id + '/vote'}
										onvote={(poll) =>
											(messages = messages.map((m) => (m.id === message.id ? { ...m, poll } : m)))}
									/>
								</div>{/if}
							{#if message.file_name}<div class="rich-content">
									<Attachment url={base() + '/' + message.id} name={message.file_name} />
								</div>{/if}
							<MessageBody content={message.content} />
						{/if}
					</div>
					{#if !message.deleted_at}<div class="message-menu">
							<MessageActions
								{message}
								onaction={(value) => action(message, value)}
								onreact={(emoji) => void react(message, emoji)}
							/>
						</div>{/if}
					{#if !message.deleted_at && message.reactions?.length}<div class="reactions">
							{#each message.reactions as reaction (reaction.emoji)}<button
									class:reacted={reaction.me}
									aria-label={`${reaction.emoji}, ${reaction.count} reactions`}
									aria-pressed={reaction.me}
									onclick={() => void react(message, reaction.emoji)}
									>{reaction.emoji}<span>{reaction.count}</span></button
								>{/each}
						</div>{/if}
				</div>
				{#if !grouped(message, messages[index + 1]) || message.edited_at || message.pinned_at}<div
						class="message-meta"
					>
						{#if message.pinned_at}<Pin size={11} /><span>Pinned</span>{/if}<time
							datetime={message.created_at}>{timeLabel(message.created_at)}</time
						>{#if message.edited_at}<span>Edited</span>{/if}
					</div>{/if}
			</article>
		{:else}<div class="intro">
				<span class="avatar"
					>{conversation.other_name
						.trim()
						.split(/\s+/)
						.slice(0, 2)
						.map((part) => part[0])
						.join('')}</span
				>
				<h3>{conversation.other_name}</h3>
				<p>A little hello goes a long way.</p>
			</div>{/each}
	</div>
	{#if replyTo}<div class="replying">
			<div>
				<strong>Replying to {replyTo.author_name}</strong>
				<p>{replyTo.content}</p>
			</div>
			<button class={chatControls.icon} aria-label="Cancel reply" onclick={() => (replyTo = null)}
				><X size={16} /></button
			>
		</div>{/if}

	{#if files?.length}<p class="attachment-chip">
			{files[0].name}
			<button
				class={chatControls.icon}
				type="button"
				aria-label="Remove attachment"
				onclick={() => (files = new DataTransfer().files)}>×</button
			>
		</p>{/if}
	<form
		class="composer"
		onsubmit={(event) => {
			event.preventDefault();
			void send();
		}}
	>
		<ComposerTools
			room={`/dms/${conversation.id}`}
			names={conversation.member_names ?? [conversation.other_name]}
			bind:files
			withPresence={false}
			onread={(id) => {
				if (autoRead) lastRead = Math.max(lastRead, id);
			}}
			onmention={(v) => (content += (content ? ' ' : '') + v + ' ')}
			onmark={() => void mark()}
			onsent={() => void refresh()}
		/>
		<Input
			onkeydown={(event) => {
				if (event.key === 'Enter') pointerSend = false;
			}}
			bind:ref={composerInput}
			aria-label={`Message ${conversation.other_name}`}
			maxlength={2000}
			placeholder={`Message ${conversation.other_name}`}
			oninput={() => presence?.typing()}
			bind:value={content}
		/>
		<EmojiPicker onpick={(v) => (content += v)} /><button
			class={chatControls.icon}
			disabled={(!content.trim() && !files?.length) || sending}
			onpointerdown={() => (pointerSend = true)}
			onpointercancel={() => (pointerSend = false)}
			aria-label="Send message"><Send size={18} /></button
		>
	</form>
	{#if typingNames.length}<small class="typing">{typingNames.join(', ')} is typing…</small>{/if}
</div>

<style>
	.sender-name {
		margin: 0 10px 5px;
		font-size: 11px;
		font-weight: 550;
		color: var(--muted);
	}
	.dm {
		--panel: #fff;
		--side: #f2f2f7;
		--well: #f2f2f7;
		--line: #d1d1d6;
		--ink: #1c1c1e;
		--muted: #6c6c70;
		--accent: #007aff;
		--danger: #ff3b30;
		--bubble-own: #007aff;
		--bubble-incoming: #e5e5ea;
		--reaction-bg: #f2f2f7;
		--reaction-border: #d1d1d6;
		--reaction-ink: #1c1c1e;
		--reaction-selected: #dbeafe;
		--reaction-selected-ink: #0756a5;
		--reaction-shadow: 0 2px 8px #0002;
		--poll-track: #d1d1d6;
		display: flex;
		flex-direction: column;
		flex: 1;
		min-width: 0;
		min-height: 0;
		position: relative;
		background: #fff;
		color: var(--ink);
	}
	@media (prefers-reduced-motion: no-preference) {
		.dm,
		.dm
			:where(
				.dm-toolbar,
				.messages,
				.message-row,
				.bubble,
				.composer,
				.recipient-avatar,
				.reactions button,
				.vote-track
			) {
			transition:
				background-color 220ms ease,
				border-color 220ms ease,
				color 220ms ease;
		}
	}
	:global([data-theme='dark']) .dm {
		--bubble-own: #0a84ff;
		--bubble-incoming: #2c2c2e;
		--panel: #1c1c1e;
		--side: #1c1c1e;
		--well: #2c2c2e;
		--line: #38383a;
		--ink: #f5f5f7;
		--muted: #98989f;
		--accent: #0a84ff;
		--danger: #ff6961;
		--reaction-bg: #2c2c2e;
		--reaction-border: #46464a;
		--reaction-ink: #f5f5f7;
		--reaction-selected: #46464a;
		--reaction-selected-ink: #fff;
		--reaction-shadow: 0 2px 8px #0008;
		--poll-track: #46464a;
		background: #000;
	}
	.dm-toolbar {
		display: flex;
		align-items: center;
		gap: 10px;
		min-height: 68px;
		flex: none;
		padding: 0 24px;
		border-bottom: 1px solid var(--line);
	}
	.recipient-avatar {
		display: grid;
		place-items: center;
		width: 34px;
		height: 34px;
		border-radius: 50%;
		background: var(--well);
		font-size: 12px;
		font-weight: 550;
		color: var(--muted);
	}
	.dm-toolbar h2 {
		flex: 1;
		min-width: 0;
		overflow-wrap: anywhere;
		margin: 0;
		font-size: 14px;
		font-weight: 550;
		letter-spacing: -0.02em;
	}
	.dm-toolbar button[aria-expanded='true'] {
		background: var(--well);
	}
	.messages {
		flex: 1;
		min-height: 0;
		overflow-y: auto;
		overscroll-behavior: contain;
		padding: 24px clamp(16px, 3vw, 40px);
		scroll-padding: 24px;
	}
	.day-divider {
		text-align: center;
		color: var(--muted);
		font-size: 11px;
		font-weight: 550;
		margin: 8px 0 24px;
	}
	.unread-divider {
		display: flex;
		align-items: center;
		gap: 12px;
		color: var(--muted);
		font-size: 10px;
		margin: 16px 0;
	}
	.unread-divider::before,
	.unread-divider::after {
		content: '';
		height: 1px;
		background: var(--line);
		flex: 1;
	}
	.message-row {
		display: flex;
		flex-direction: column;
		align-items: flex-start;
		margin: 18px 0;
	}
	.message-row.grouped {
		margin-top: -12px;
	}
	.message-row.mine {
		align-items: flex-end;
	}
	.message-line {
		display: flex;
		align-items: center;
		position: relative;
		gap: 5px;
		max-width: min(86%, 620px);
		min-width: 0;
	}
	.bubble {
		min-width: 0;
		padding: 11px 16px;
		border-radius: 20px 20px 20px 6px;
		background: var(--bubble-incoming);
		font-size: 15px;
		line-height: 1.6;
		color: var(--ink);
		overflow-wrap: anywhere;
	}
	.mine .bubble {
		background: var(--bubble-own);
		color: white;
		border-radius: 20px 20px 6px 20px;
	}
	.bubble.deleted {
		background: transparent;
		padding: 8px 0;
		font-size: 13px;
		color: var(--muted);
		font-style: italic;
	}
	.bubble :global(.body > :first-child) {
		margin-top: 0;
	}
	.bubble :global(.body > :last-child) {
		margin-bottom: 0;
	}
	.bubble :global(.body p) {
		margin: 0 0 8px;
	}
	.bubble :global(.body pre) {
		max-width: 100%;
		border-radius: 10px;
		font-size: 12px;
		margin-block: 10px;
	}
	.bubble :global(.body a) {
		color: inherit;
		text-underline-offset: 3px;
	}
	.message-menu {
		flex: none;
	}
	.mine .message-menu {
		order: -1;
	}
	.message-meta {
		display: flex;
		align-items: center;
		gap: 5px;
		padding: 5px 10px 0;
		font-size: 10px;
		color: var(--muted);
	}
	.reactions {
		position: absolute;
		z-index: 1;
		top: -14px;
		right: 40px;
		display: flex;
		flex-wrap: nowrap;
		gap: 4px;
		margin: 0;
		padding: 0;
		background: transparent;
	}
	.mine .reactions {
		right: 0;
	}
	.reactions button {
		display: inline-flex;
		align-items: center;
		gap: 3px;
		min-height: 30px;
		min-width: 30px;
		border: 1px solid var(--reaction-border);
		border-radius: 15px;
		padding: 3px 6px;
		background: var(--reaction-bg);
		color: var(--reaction-ink);
		box-shadow: var(--reaction-shadow);
		cursor: pointer;
	}
	.reactions button.reacted {
		background: var(--reaction-selected);
		color: var(--reaction-selected-ink);
	}
	.reactions span {
		font-size: 9px;
		font-weight: 600;
	}
	.reply-preview {
		padding-left: 10px;
		border-left: 2px solid currentColor;
		margin: 2px 0 10px;
		opacity: 0.8;
		font-size: 12px;
	}
	.reply-preview span {
		font-size: 10px;
		font-weight: 600;
	}
	.reply-preview p {
		display: -webkit-box;
		-webkit-line-clamp: 2;
		line-clamp: 2;
		-webkit-box-orient: vertical;
		overflow: hidden;
		margin: 3px 0 0;
	}
	.rich-content {
		background: var(--panel);
		color: var(--ink);
		border-radius: 12px;
		padding: 10px;
		margin-bottom: 8px;
	}
	.rich-content :global(button) {
		max-width: 100%;
		overflow-wrap: anywhere;
		white-space: normal;
	}
	.older {
		display: block;
		margin: 0 auto 20px;
	}
	.edit {
		min-width: min(240px, 40vw);
	}
	.edit > div {
		display: flex;
		justify-content: flex-end;
		gap: 6px;
		margin-top: 8px;
	}
	.edit :global(input) {
		width: 100%;
		color: var(--ink);
		background: var(--panel);
	}
	.replying {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 16px;
		margin: 4px 24px;
		padding: 12px 14px;
		border-left: 2px solid var(--accent);
		background: var(--side);
		border-radius: 4px 10px 10px 4px;
	}
	.replying div {
		min-width: 0;
	}
	.replying strong {
		font-size: 11px;
		font-weight: 550;
	}
	.replying p {
		font-size: 12px;
		color: var(--muted);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		margin: 3px 0 0;
	}
	.composer {
		display: flex;
		align-items: center;
		flex: none;
	}
	.composer :global(input) {
		flex: 1;
		min-width: 0;
	}
	.composer button:disabled {
		opacity: 0.4;
	}
	.attachment-chip {
		margin: 4px 24px;
		font-size: 12px;
	}
	.typing {
		position: absolute;
		bottom: 0;
		left: 24px;
		font-size: 10px;
		color: var(--muted);
	}
	.error {
		margin: 12px 24px;
		color: var(--danger);
		font-size: 13px;
	}
	.intro {
		text-align: center;
		margin: 48px auto;
		padding: 24px;
	}
	.avatar {
		display: inline-grid;
		place-items: center;
		width: 56px;
		height: 56px;
		border-radius: 50%;
		background: var(--well);
		font-size: 18px;
		color: var(--muted);
	}
	.intro h3 {
		font-size: 24px;
		font-weight: 500;
		letter-spacing: -0.035em;
		margin: 18px 0 8px;
	}
	.intro p {
		font-size: 13px;
		color: var(--muted);
	}
	.dm-panel {
		padding: 16px 24px;
		background: var(--side);
		border-bottom: 1px solid var(--line);
		max-height: 36dvh;
		overflow-y: auto;
	}
	.dm-panel h3 {
		font-size: 13px;
		font-weight: 550;
		margin: 0 0 12px;
	}
	.dm-panel p {
		font-size: 13px;
		line-height: 1.6;
		overflow-wrap: anywhere;
	}
	.dm-panel :global(form),
	.dm-panel :global(label) {
		display: flex;
		align-items: center;
		gap: 8px;
		flex-wrap: wrap;
	}
	.dm-panel :global(input),
	.dm-panel :global(select) {
		min-width: 0;
		max-width: 100%;
	}
	@media (hover: hover) and (pointer: fine) {
		.message-menu {
			opacity: 0;
			transition: opacity 120ms ease;
		}
		.message-row:hover .message-menu,
		.message-row:focus-within .message-menu {
			opacity: 1;
		}
	}
	@media (prefers-reduced-motion: no-preference) {
		.bubble.arriving {
			transition:
				transform 180ms var(--ease-out),
				opacity 180ms var(--ease-out);
		}
		@starting-style {
			.bubble.arriving {
				opacity: 0;
				transform: translateY(6px) scale(0.98);
			}
		}
		.reactions button {
			transition: transform 120ms var(--ease-out);
		}
		.reactions button:active:not(:focus-visible) {
			transform: scale(0.94);
		}
	}
	@media (max-width: 700px) {
		.dm-toolbar {
			min-height: 58px;
			padding-inline: 14px;
			gap: 6px;
		}
		.message-line {
			max-width: 94%;
		}
		.messages {
			padding-inline: 14px;
		}
		.message-row {
			margin-block: 16px;
		}
		.bubble {
			font-size: 15px;
			padding: 10px 14px;
		}
		.composer :global(input) {
			font-size: 16px;
		}
	}
</style>
