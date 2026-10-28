<script lang="ts">
	import { communityRequest, type DirectConversation, type DirectMessage } from './communities';

	let { conversation }: { conversation: DirectConversation } = $props();
	let messages = $state<DirectMessage[]>([]);
	let hasOlder = $state(false);
	let content = $state('');
	let replyTo = $state<DirectMessage | null>(null);
	let editingId = $state<number | null>(null);
	let draft = $state('');
	let error = $state('');
	let sending = $state(false);
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
			hasOlder = page.has_more;
			error = '';
		} catch (cause) {
			if (current === generation) error = problem(cause);
		}
	}

	async function refresh() {
		if (polling || document.visibilityState !== 'visible') return;
		polling = true;
		const current = generation;
		try {
			const page = await communityRequest<{ items: DirectMessage[] }>(base());
			if (current === generation) {
				const first = page.items[0]?.id;
				const retained = first ? messages.filter((item) => item.id < first) : [];
				const older = retained.slice(-200);
				messages = [...older, ...page.items];
				hasOlder ||= retained.length > older.length;
			}
		} catch (cause) {
			if (current === generation) error = problem(cause);
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
		if (!content.trim() || sending) return;
		sending = true;
		try {
			const sent = await communityRequest<DirectMessage>(base(), 'POST', {
				content,
				...(replyTo ? { reply_to: replyTo.id } : {})
			});
			messages = [...messages, sent];
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
	<h2>Direct message with {conversation.other_name}</h2>
	<p class="muted">Only the two of you can read this conversation.</p>
	{#if error}<p class="error" role="alert">{error}</p>{/if}
	<div class="messages" aria-live="polite">
		{#if hasOlder}<button onclick={() => void older()}>Load older messages</button>{/if}
		{#each messages as message (message.id)}
			<article>
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
						<input aria-label="Edit direct message" maxlength="2000" bind:value={draft} />
						<button disabled={!draft.trim()}>Save</button><button
							type="button"
							onclick={() => (editingId = null)}>Cancel</button
						>
					</form>
				{:else}<p>
						{message.deleted_at ? 'Message deleted' : message.content}{message.edited_at
							? ' (edited)'
							: ''}
					</p>{/if}
				{#if !message.deleted_at}<div class="actions">
						<button onclick={() => (replyTo = message)}>Reply</button>
						{#if message.mine}<button
								onclick={() => {
									editingId = message.id;
									draft = message.content;
								}}>Edit</button
							><button
								onclick={() => {
									if (confirm('Delete this message?')) void change(message, 'DELETE');
								}}>Delete</button
							>{/if}
					</div>{/if}
			</article>
		{:else}<p class="muted">No messages yet. Say hello.</p>{/each}
	</div>
	{#if replyTo}<p class="replying">
			Replying to {replyTo.author_name} <button onclick={() => (replyTo = null)}>Cancel</button>
		</p>{/if}
	<form
		class="composer"
		onsubmit={(event) => {
			event.preventDefault();
			void send();
		}}
	>
		<input
			aria-label={`Message ${conversation.other_name}`}
			maxlength="2000"
			placeholder={`Message ${conversation.other_name}`}
			bind:value={content}
		/>
		<button disabled={!content.trim() || sending}>Send</button>
	</form>
</div>

<style>
	.dm {
		border: 1px solid #eee1e4;
		border-radius: 12px;
		padding: 20px;
	}
	h2 {
		margin: 0;
	}
	.muted,
	time,
	small {
		color: #746c70;
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
		min-height: 260px;
		max-height: 520px;
		overflow-y: auto;
		margin: 20px 0;
	}
	article {
		padding: 12px 0;
		border-bottom: 1px solid #f2ecee;
	}
	article p {
		margin: 6px 0;
		white-space: pre-wrap;
		overflow-wrap: anywhere;
	}
	.actions button {
		font-size: 12px;
		padding: 3px 7px;
	}
	.composer input,
	.edit input {
		flex: 1;
	}
	input {
		border: 1px solid #d8cdd0;
		border-radius: 7px;
		padding: 9px;
		font: inherit;
	}
	button {
		cursor: pointer;
		border: 1px solid #ddd2d5;
		border-radius: 7px;
		background: white;
		padding: 6px 10px;
	}
	button:disabled {
		opacity: 0.5;
		cursor: default;
	}
	.error {
		color: #a51f3b;
	}
</style>
