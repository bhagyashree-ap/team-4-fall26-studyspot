<script lang="ts">
	import { chatControls } from '$lib/chatControls';
	import * as Card from '$lib/components/ui/card';
	import { Badge } from '$lib/components/ui/badge';
	import X from '@lucide/svelte/icons/x';
	import Inbox from '@lucide/svelte/icons/inbox';
	import { resolve } from '$app/paths';
	import { onMount } from 'svelte';
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
	onMount(() => {
		let busy = false;
		async function refresh() {
			if (document.hidden || busy) return;
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
	id={panelId}
	bind:this={panel}
	popover="auto"
	role="dialog"
	aria-label="Notification inbox"
>
	<header>
		<Inbox size={19} />
		<h2>Inbox</h2>
		{#if items.length}<Badge variant="secondary">{items.length} unread</Badge>{/if}<button
			class="chat-icon {chatControls.icon}"
			aria-label="Close inbox"
			onclick={() => panel.hidePopover()}><X size={16} /></button
		>
	</header>
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
		margin-left: auto;
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
</style>
