<script lang="ts">
	import { chatControls } from '$lib/chatControls';
	import { Input } from '$lib/components/ui/input';
	import Settings from '@lucide/svelte/icons/settings';
	import Pin from '@lucide/svelte/icons/pin';
	import Search from '@lucide/svelte/icons/search';
	import AtSign from '@lucide/svelte/icons/at-sign';
	import Presence from './Presence.svelte';
	import SearchMessages from './SearchMessages.svelte';
	import MessageLink from './MessageLink.svelte';
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

	let { conversation }: { conversation: DirectConversation } = $props();
	let messages = $state<DirectMessage[]>([]);
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
	async function mark(unread_from?: number) {
		try {
			const result = await communityRequest<{ last_read: number }>(
				`/dms/${conversation.id}` + '/read',
				'PUT',
				unread_from ? { unread_from } : {}
			);
			lastRead = result.last_read;
		} catch (e) {
			error = problem(e);
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
			const merged = mergeMessages(messages, page.updates);
			hasOlder ||= merged.length > 250;
			messages = merged.slice(-250);

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
			const page = await communityRequest<{ items: DirectMessage[]; has_more: boolean }>(
				`${base()}?before=${messages[0].id}`
			);
			messages = [...page.items, ...messages];
			hasOlder = page.has_more;
		} catch (cause) {
			error = problem(cause);
		}
	}

	async function send() {
		if ((!content.trim() && !files?.length) || sending) return;
		sending = true;
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
			messages = mergeMessages(messages, [sent]);
			files = new DataTransfer().files;
			content = '';
			replyTo = null;
			error = '';
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

<div class="dm">
	<header class="dm-toolbar">
		<AtSign size={21} />
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
			onread={(id) => (lastRead = id)}
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
	<div class="messages" aria-live="polite">
		{#if hasOlder}<button class={chatControls.ghost} onclick={() => void older()}
				>Load older messages</button
			>{/if}
		{#each messages as message (message.id)}
			{#if message.id > lastRead && messages.find((m) => m.id > lastRead)?.id === message.id}<div
					class="unread-divider"
				>
					Unread messages
				</div>{/if}
			<article id={`message-${message.id}`}>
				<div class="heading">
					<strong>{message.author_name}</strong><time datetime={message.created_at}
						>{new Date(message.created_at).toLocaleString()}</time
					>
				</div>
				{#if message.reply_to}<small>↳ Reply to message #{message.reply_to}</small>{/if}
				{#if editingId === message.id}
					<form
						class="edit"
						onsubmit={(event) => {
							event.preventDefault();
							void change(message, 'PATCH');
						}}
					>
						<Input aria-label="Edit direct message" maxlength={2000} bind:value={draft} />
						<button class={chatControls.ghost} disabled={!draft.trim()}>Save</button><button
							class={chatControls.ghost}
							type="button"
							onclick={() => (editingId = null)}>Cancel</button
						>
					</form>
				{:else}{#if message.deleted_at}Message deleted{:else}{#if message.poll}<Ballot
								poll={message.poll}
								url={base() + '/' + message.id + '/vote'}
								onvote={(poll) =>
									(messages = messages.map((m) => (m.id === message.id ? { ...m, poll } : m)))}
							/>{/if}{#if message.file_name}<Attachment
								url={base() + '/' + message.id}
								name={message.file_name}
							/>{/if}<MessageBody content={message.content} />{#if message.edited_at}<small
								>(edited)</small
							>{/if}{/if}{/if}
				{#if !message.deleted_at}<div class="actions">
						<button class={chatControls.ghost} onclick={() => void pin(message)}
							>{message.pinned_at ? 'Unpin' : 'Pin'}</button
						>
						<EmojiPicker reaction onpick={(emoji) => void react(message, emoji)} />
						{#each message.reactions ?? [] as r (r.emoji)}<button
								class={chatControls.ghost}
								aria-pressed={r.me}
								onclick={() => void react(message, r.emoji)}>{r.emoji} {r.count}</button
							>{/each}
						<button class={chatControls.ghost} onclick={() => (thread = message)}>Thread</button
						><button class={chatControls.ghost} onclick={() => void mark(message.id)}
							>Mark unread</button
						><MessageLink id={message.id} />
						<button class={chatControls.ghost} onclick={() => (replyTo = message)}>Reply</button>
						{#if message.mine}<button
								class={chatControls.ghost}
								onclick={() => {
									editingId = message.id;
									draft = message.content;
								}}>Edit</button
							><button
								class={chatControls.ghost}
								onclick={() => {
									if (confirm('Delete this message?')) void change(message, 'DELETE');
								}}>Delete</button
							>{/if}
					</div>{/if}
			</article>
		{:else}<div class="intro">
				<div class="avatar">
					{conversation.other_name
						.split(' ')
						.map((part) => part[0])
						.slice(0, 2)
						.join('')}
				</div>
				<h3>{conversation.other_name}</h3>
				<p>This is the beginning of your private conversation.</p>
			</div>{/each}
	</div>
	{#if replyTo}<p class="replying">
			Replying to {replyTo.author_name}
			<button class={chatControls.ghost} onclick={() => (replyTo = null)}>Cancel</button>
		</p>{/if}

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
			names={[conversation.other_name]}
			bind:files
			withPresence={false}
			onread={(id) => (lastRead = id)}
			onmention={(v) => (content += (content ? ' ' : '') + v + ' ')}
			onmark={() => void mark()}
			onsent={() => void refresh()}
		/>
		<Input
			aria-label={`Message ${conversation.other_name}`}
			maxlength={2000}
			placeholder={`Message ${conversation.other_name}`}
			oninput={() => presence?.typing()}
			bind:value={content}
		/>
		<EmojiPicker onpick={(v) => (content += v)} /><button
			class={chatControls.icon}
			disabled={(!content.trim() && !files?.length) || sending}
			aria-label="Send message"><Send size={18} /></button
		>
	</form>
	{#if typingNames.length}<small class="typing">{typingNames.join(', ')} is typing…</small>{/if}
</div>

<style>
	.unread-divider {
		border-top: 1px solid var(--accent);
		color: var(--accent);
		font-size: 0.8rem;
		text-align: center;
	}
	.dm {
		position: relative;
	}
	.dm {
		display: flex;
		flex-direction: column;
		flex: 1;
		min-height: 0;
		min-width: 0;
	}
	h2 {
		margin: 0;
	}
	time,
	small {
		color: var(--muted);
	}
	time {
		font-size: 12px;
	}
	.heading,
	.actions,
	.composer,
	.edit {
		display: flex;
		align-items: center;
		gap: 10px;
	}
	.messages {
		min-height: 160px;
		flex: 1;
		overflow-y: auto;
		padding: 16px 22px;
	}
	article {
		padding: 12px 0;
		border-bottom: 1px solid var(--line);
	}
	.actions {
		flex-wrap: wrap;
	}
	.actions button {
		font-size: 12px;
		padding: 3px 7px;
	}
	.composer :global(input),
	.edit :global(input) {
		flex: 1;
	}
	.dm :global(input) {
		border: 1px solid var(--line);
		border-radius: 7px;
		padding: 9px;
		font: inherit;
	}
	button {
		cursor: pointer;
		border: 1px solid var(--line);
		border-radius: 7px;
		background: var(--panel);
		padding: 6px 10px;
	}
	button:disabled {
		opacity: 0.5;
		cursor: default;
	}
	.error {
		color: var(--danger);
	}
	.dm-toolbar {
		display: flex;
		align-items: center;
		gap: 6px;
		padding: 0 16px;
		height: 52px;
		flex: none;
		border-bottom: 1px solid var(--line);
		color: var(--muted);
	}
	.dm-toolbar h2 {
		flex: 1;
		color: var(--ink);
		font-weight: 650;
		font-size: 16px;
	}
	.dm-toolbar [aria-expanded='true'] {
		background: var(--selected);
	}
	.dm-panel {
		padding: 14px 20px;
		background: var(--side);
		border-bottom: 1px solid var(--line);
		max-height: 40vh;
		overflow: auto;
	}
	.dm-panel h3 {
		font-weight: 650;
		margin: 0 0 10px;
	}
	.dm-panel :global(form),
	.dm-panel :global(label) {
		display: flex;
		align-items: center;
		gap: 8px;
		flex-wrap: wrap;
	}
	.dm-panel :global(input),
	.dm-panel :global(select),
	.dm-panel :global(button) {
		background: var(--well);
		border: 1px solid var(--line);
		border-radius: 6px;
		padding: 6px 9px;
		min-width: 0;
		max-width: 100%;
	}
	.dm-panel p,
	.intro p {
		color: var(--muted);
	}
	.intro {
		margin-top: clamp(30px, 10vh, 100px);
	}
	.intro h3 {
		font-size: 24px;
		font-weight: 700;
		margin: 12px 0 4px;
	}
	.avatar {
		display: grid;
		place-items: center;
		width: 58px;
		height: 58px;
		border-radius: 50%;
		background: #5865a5;
		color: white;
		font-size: 20px;
		font-weight: 650;
	}
	.typing {
		position: absolute;
		bottom: 2px;
		left: 22px;
	}
</style>
