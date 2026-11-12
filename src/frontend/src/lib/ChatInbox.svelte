<script lang="ts">
	import { chatControls } from '$lib/chatControls';
	import * as Card from '$lib/components/ui/card';
	import { Badge } from '$lib/components/ui/badge';
	import X from '@lucide/svelte/icons/x';
	import Inbox from '@lucide/svelte/icons/inbox';
	import { resolve } from '$app/paths';
	import { onMount } from 'svelte';
	import { SvelteMap } from 'svelte/reactivity';
	import { communityRequest } from './communities';
	type Notice = {
		id: number;
		created_at: string;
		channel__community__name?: string;
		channel__name?: string;
		author_name: string;
		content: string;
		channel_id?: number;
		channel__community_id?: number;
		conversation_id?: number;
	};
	const panelId = $props.id();
	let panel: HTMLDivElement;
	let pending = $state(true);
	const formatTime = new Intl.DateTimeFormat(undefined, {
		month: 'short',
		day: 'numeric',
		hour: 'numeric',
		minute: '2-digit'
	});
	let items = $state<Notice[]>([]),
		error = $state('');
	let clearing = $state(false);
	let confirmClear = $state(false);
	async function clearAll() {
		if (!items.length || clearing) return;
		clearing = true;
		const latestByRoom = new SvelteMap<string, Notice>();
		for (const item of items) {
			const key = item.conversation_id
				? `dm:${item.conversation_id}`
				: `channel:${item.channel__community_id}:${item.channel_id}`;
			const current = latestByRoom.get(key);
			if (!current || item.id > current.id) latestByRoom.set(key, item);
		}
		try {
			await Promise.all(
				[...latestByRoom.values()].map((item) =>
					item.conversation_id
						? communityRequest(`/dms/${item.conversation_id}/read`, 'PUT', {
								read_through: item.id
							})
						: communityRequest(
								`/communities/${item.channel__community_id}/channels/${item.channel_id}/read`,
								'PUT',
								{ read_through: item.id }
							)
				)
			);
			await new Promise((resolve) => window.setTimeout(resolve, 180));
			items = [];
			confirmClear = false;
			error = '';
		} catch (cause) {
			error = cause instanceof Error ? cause.message : 'Could not clear your inbox';
		} finally {
			clearing = false;
		}
	}
	onMount(() => {
		let busy = false;
		async function refresh() {
			if (document.hidden || busy || clearing) return;
			busy = true;
			try {
				items = (await communityRequest<{ items: Notice[] }>('/chat/notifications')).items;
				error = '';
			} catch (e) {
				error = e instanceof Error ? e.message : 'Inbox unavailable';
			} finally {
				busy = false;
				pending = false;
			}
		}
		void refresh();
		const timer = setInterval(refresh, 8000);
		return () => clearInterval(timer);
	});
</script>

<button
	class="chat-icon inbox-trigger {chatControls.icon}"
	popovertarget={panelId}
	aria-label="Notification inbox"
	title="Inbox"
	><Inbox size={18} />{#if items.length}<i></i>{/if}</button
>
<div
	class="inbox-panel"
	class:clearing
	id={panelId}
	bind:this={panel}
	popover="auto"
	role="dialog"
	aria-label="Notification inbox"
>
	<header>
		<Inbox size={19} />
		<h2>Inbox</h2>
		{#if items.length}<Badge variant="secondary">{items.length} unread</Badge><button
				class="clear-all"
				disabled={clearing}
				onclick={() => (confirmClear = !confirmClear)}
				>{clearing ? 'Clearing…' : 'Clear all'}</button
			>{/if}<button
			class="chat-icon {chatControls.icon}"
			aria-label="Close inbox"
			onclick={() => panel.hidePopover()}><X size={16} /></button
		>
	</header>
	{#if confirmClear}
		<div class="clear-confirm" role="group" aria-label="Clear unread inbox messages">
			<div>
				<strong>Clear your inbox?</strong>
				<p>All current unread messages will be marked as read.</p>
			</div>
			<div class="confirm-actions">
				<button class="cancel-clear" disabled={clearing} onclick={() => (confirmClear = false)}
					>Cancel</button
				>
				<button class="confirm-clear" disabled={clearing} onclick={() => void clearAll()}>
					{clearing ? 'Clearing…' : 'Clear all'}
				</button>
			</div>
		</div>
	{/if}
	<div class="notices">
		{#if error}<p role="alert">{error}</p>{/if}
		{#each items as item ((item.conversation_id ? 'dm' : 'ch') + item.id)}
			<a
				data-sveltekit-reload
				href={resolve(
					`/communities?${item.conversation_id ? 'dm=' + item.conversation_id : 'id=' + item.channel__community_id + '&channel=' + item.channel_id}#message-${item.id}`
				)}
			>
				<Card.Root size="sm" class="notice-card">
					<div class="context">
						<span
							>{item.conversation_id
								? 'Direct message'
								: (item.channel__community__name ?? 'Community') +
									' · #' +
									(item.channel__name ?? 'channel')}</span
						><time datetime={item.created_at}>{formatTime.format(new Date(item.created_at))}</time>
					</div>
					<strong>{item.author_name}</strong>
					<p>{item.content || 'Attachment'}</p></Card.Root
				></a
			>
		{:else}{#if !error}<div class="empty">
					<Inbox size={28} /><strong>{pending ? 'Loading inbox…' : 'You’re all caught up'}</strong>
					<p>Unread messages from your channels and DMs appear here.</p>
				</div>{/if}{/each}
	</div>
</div>

<style>
	.inbox-trigger {
		position: relative;
	}
	i {
		position: absolute;
		right: 4px;
		top: 4px;
		width: 6px;
		height: 6px;
		background: var(--accent);
		border-radius: 50%;
	}
	.inbox-panel {
		position: fixed;
		inset: calc(var(--site-header-height, 0px) + 48px) 12px auto auto;
		margin: 0;
		width: min(420px, calc(100% - 24px));
		max-height: min(620px, calc(100dvh - var(--site-header-height, 0px) - 68px));
		border: 1px solid var(--line);
		border-radius: 14px;
		background: var(--side);
		color: var(--ink);
		box-shadow: 0 16px 48px #0004;
		padding: 0;
	}
	.inbox-panel:popover-open {
		display: flex;
		flex-direction: column;
	}
	.inbox-panel {
		opacity: 1;
		transform: translateY(0);
		transition:
			opacity 160ms var(--ease-out),
			transform 180ms var(--ease-out);
		@starting-style {
			opacity: 0;
			transform: translateY(-7px);
		}
	}
	header {
		display: flex;
		align-items: center;
		gap: 9px;
		padding: 12px 14px;
		border-bottom: 1px solid var(--line);
		background: var(--panel);
	}
	header h2 {
		font-size: 16px;
		font-weight: 700;
	}
	header button {
		margin-left: 0;
	}
	header .clear-all {
		margin-left: auto;
		padding: 5px 8px;
		border: 0;
		border-radius: 8px;
		background: transparent;
		color: var(--accent);
		font: inherit;
		font-size: 12px;
		font-weight: 650;
		cursor: pointer;
	}
	header .clear-all:hover:not(:disabled) {
		background: var(--well);
	}
	header .clear-all:disabled {
		cursor: wait;
		opacity: 0.65;
	}
	.notices {
		display: grid;
		gap: 8px;
		padding: 10px;
		overflow: auto;
		overscroll-behavior: contain;
	}
	.notices a {
		display: block;
		min-width: 0;
		border-radius: 10px;
	}
	.notices :global(.notice-card) {
		padding: 12px 14px;
		gap: 4px;
		background: var(--panel);
		border: 1px solid var(--line);
		box-shadow: none;
		transition:
			transform 180ms var(--ease-out),
			border-color 140ms ease,
			opacity 160ms ease;
		@starting-style {
			transform: translateY(7px);
			opacity: 0;
		}
	}
	.notices a:hover :global(.notice-card) {
		transform: translateY(-2px);
	}
	.inbox-panel.clearing :global(.notice-card) {
		transform: translateX(10px);
		opacity: 0;
	}
	.notices a:hover :global(.notice-card),
	.notices a:focus-visible :global(.notice-card) {
		border-color: var(--accent);
	}
	.context {
		display: flex;
		align-items: baseline;
		justify-content: space-between;
		gap: 10px;
		font-size: 11px;
		color: var(--muted);
	}
	.context span {
		min-width: 0;
		overflow-wrap: anywhere;
	}
	time {
		flex: none;
	}
	.notices p {
		font-size: 13px;
		line-height: 1.45;
		overflow-wrap: anywhere;
		color: var(--muted);
	}
	.notices a p {
		display: -webkit-box;
		-webkit-line-clamp: 3;
		line-clamp: 3;
		-webkit-box-orient: vertical;
		overflow: hidden;
	}
	.empty {
		display: grid;
		justify-items: center;
		gap: 8px;
		padding: 26px 16px;
		text-align: center;
	}
	.clear-confirm {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 14px;
		margin: 10px 10px 0;
		padding: 12px;
		border: 1px solid var(--line);
		border-radius: 12px;
		background: var(--panel);
		box-shadow: 0 8px 24px #0000000b;
		animation: inbox-confirm-in 160ms var(--ease-out) both;
	}
	.clear-confirm p {
		margin-top: 3px;
		font-size: 12px;
		color: var(--muted);
	}
	.confirm-actions {
		display: flex;
		align-items: center;
		gap: 5px;
		flex: none;
	}
	.confirm-actions button {
		padding: 7px 9px;
		border: 0;
		border-radius: 8px;
		font: inherit;
		font-size: 12px;
		font-weight: 650;
		cursor: pointer;
	}
	.cancel-clear {
		background: var(--well);
		color: var(--ink);
	}
	.confirm-clear {
		background: var(--accent);
		color: white;
	}
	.confirm-actions button:disabled {
		opacity: 0.65;
		cursor: wait;
	}
	@keyframes inbox-confirm-in {
		from {
			opacity: 0;
			transform: translateY(-5px);
		}
		to {
			opacity: 1;
			transform: translateY(0);
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.notices :global(.notice-card),
		.clear-confirm {
			animation: none;
			transition-duration: 100ms;
		}
		.inbox-panel.clearing :global(.notice-card) {
			transform: none;
		}
	}
</style>
