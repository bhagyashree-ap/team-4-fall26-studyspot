<script lang="ts">
	import { tick, type Snippet } from 'svelte';
	import Plus from '@lucide/svelte/icons/plus';
	import Users from '@lucide/svelte/icons/users';
	import Search from '@lucide/svelte/icons/search';
	import SquarePen from '@lucide/svelte/icons/square-pen';
	import X from '@lucide/svelte/icons/x';
	import ArrowLeft from '@lucide/svelte/icons/arrow-left';
	import MessagesSquare from '@lucide/svelte/icons/messages-square';
	import ArrowUpRight from '@lucide/svelte/icons/arrow-up-right';
	import MoreHorizontal from '@lucide/svelte/icons/ellipsis';
	import Pin from '@lucide/svelte/icons/pin';
	import Trash2 from '@lucide/svelte/icons/trash-2';
	import CircleDot from '@lucide/svelte/icons/circle-dot';
	import Sun from '@lucide/svelte/icons/sun';
	import Moon from '@lucide/svelte/icons/moon';
	import type { DirectConversation } from './communities';

	let {
		conversations,
		selected,
		loading = false,
		error = '',
		onselect,
		onback,
		backLabel = 'Communities',
		onnew,
		onnewgroup,
		theme = 'light',
		ontheme,
		onconversationaction,
		conversationView,
		composing = false,
		composeView
	}: {
		conversations: DirectConversation[];
		selected: DirectConversation | null;
		loading?: boolean;
		error?: string;
		onselect: (conversation: DirectConversation | null) => void;
		onback: () => void;
		backLabel?: string;
		onnew: () => void;
		onnewgroup: () => void;
		theme?: 'light' | 'dark';
		ontheme?: () => void;
		onconversationaction?: (action: 'pin' | 'delete' | 'unread', item: DirectConversation) => void;
		conversationView: Snippet<[DirectConversation]>;
		composing?: boolean;
		composeView?: Snippet;
	} = $props();
	let readingPane: HTMLElement;
	let searchInput: HTMLInputElement;
	let query = $state('');
	let createMenu: HTMLDivElement;
	let createTrigger: HTMLButtonElement;
	let actionMenu: HTMLDivElement;
	let actionTrigger: HTMLButtonElement;
	let actionOpen = $state(false);
	let actionItem = $state<DirectConversation | null>(null);
	$effect(() => {
		if (!actionOpen) return;
		const dismiss = (event: Event) => {
			if (
				event.target instanceof Node &&
				(actionMenu.contains(event.target) || actionTrigger?.contains(event.target))
			)
				return;
			actionMenu.hidePopover();
		};
		window.addEventListener('pointerdown', dismiss, true);
		window.addEventListener('scroll', dismiss, true);
		window.addEventListener('resize', dismiss);
		return () => {
			window.removeEventListener('pointerdown', dismiss, true);
			window.removeEventListener('scroll', dismiss, true);
			window.removeEventListener('resize', dismiss);
		};
	});
	const unreadTotal = $derived(
		conversations.reduce((total, item) => total + (item.unread_count ?? 0), 0)
	);
	function openCreate(event: MouseEvent) {
		if (createMenu.matches(':popover-open')) {
			createMenu.hidePopover();
			return;
		}
		createMenu.showPopover();
		const rect = createTrigger.getBoundingClientRect();
		createMenu.style.left =
			Math.max(
				12,
				Math.min(rect.right - createMenu.offsetWidth, innerWidth - createMenu.offsetWidth - 12)
			) + 'px';
		createMenu.style.top = rect.bottom + 8 + 'px';
		if (event.detail === 0) createMenu.querySelector<HTMLButtonElement>('button')?.focus();
	}
	const matching = $derived(
		conversations
			.slice()
			.sort((a, b) => Number(Boolean(b.pinned)) - Number(Boolean(a.pinned)))
			.filter((item) =>
				item.other_name.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase())
			)
	);
	function openActions(event: MouseEvent, item: DirectConversation) {
		const fromContextMenu = event.type === 'contextmenu';
		if (fromContextMenu) event.preventDefault();
		event.stopPropagation();
		actionItem = item;
		if (actionMenu.matches(':popover-open') && !fromContextMenu) {
			actionMenu.hidePopover();
			actionOpen = false;
			return;
		}
		if (actionMenu.matches(':popover-open')) actionMenu.hidePopover();
		actionMenu.showPopover();
		actionOpen = true;
		if (fromContextMenu) {
			actionMenu.style.left =
				Math.max(12, Math.min(event.clientX, innerWidth - actionMenu.offsetWidth - 12)) + 'px';
			actionMenu.style.top =
				Math.max(12, Math.min(event.clientY, innerHeight - actionMenu.offsetHeight - 12)) + 'px';
			actionMenu.querySelector<HTMLButtonElement>('[role="menuitem"]')?.focus();
		} else {
			const rect = actionTrigger.getBoundingClientRect();
			actionMenu.style.left =
				Math.max(
					12,
					Math.min(rect.right - actionMenu.offsetWidth, innerWidth - actionMenu.offsetWidth - 12)
				) + 'px';
			actionMenu.style.top =
				Math.min(rect.bottom + 6, innerHeight - actionMenu.offsetHeight - 12) + 'px';
		}
	}
	function conversationAction(action: 'pin' | 'delete' | 'unread') {
		if (!actionItem) return;
		if (action === 'delete' && selected?.id === actionItem.id) onselect(null);
		onconversationaction?.(action, actionItem);
		actionMenu.hidePopover();
		actionOpen = false;
	}
	async function choose(conversation: DirectConversation | null) {
		onselect(conversation);
		await tick();
		if (matchMedia('(max-width: 700px)').matches) {
			if (conversation) readingPane.focus();
			else searchInput.focus();
		}
	}

	function initials(name: string) {
		return name
			.trim()
			.split(/\s+/)
			.slice(0, 2)
			.map((part) => part[0])
			.join('')
			.toUpperCase();
	}
	function date(value: string) {
		const time = new Date(value);
		return Number.isNaN(time.getTime())
			? ''
			: time.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
	}
</script>

<section class="inbox" aria-labelledby="inbox-title">
	<header class="inbox-heading">
		<div class="title-group">
			<h1 id="inbox-title" aria-label="Messages">
				<button
					class="inbox-home"
					aria-label="Messages"
					onclick={() => {
						query = '';
						void choose(null);
					}}
				>
					<span class="inbox-mark" aria-hidden="true"
						><MessagesSquare size={19} strokeWidth={1.5} />{#if unreadTotal}<span
								class="icon-unread">{unreadTotal > 99 ? '99+' : unreadTotal}</span
							>{/if}</span
					>
					<span class="home-copy"
						><span>Messages</span><small aria-hidden="true">A space for your conversations.</small
						></span
					>
				</button>
			</h1>
		</div>
		<div class="header-actions">
			<button
				class="theme-toggle"
				aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
				onclick={ontheme}
			>
				{#if theme === 'dark'}<Sun size={16} />{:else}<Moon size={16} />{/if}<span
					>{theme === 'dark' ? 'Light' : 'Dark'}</span
				>
			</button><button class="back-button" onclick={onback}
				><ArrowLeft size={16} /><span>Back to {backLabel}</span></button
			>
		</div>
	</header>
	<div class="inbox-layout" class:has-conversation={selected !== null || composing}>
		<section class="conversation-pane" aria-label="Conversations">
			<div class="list-heading">
				<h3>Your conversations</h3>
				<button
					class="create-trigger"
					bind:this={createTrigger}
					aria-label="Create conversation"
					aria-haspopup="dialog"
					onclick={openCreate}><Plus size={19} /></button
				>
				<div
					class="create-menu"
					popover="auto"
					bind:this={createMenu}
					role="dialog"
					tabindex="-1"
					aria-label="Create conversation"
					onkeydown={(event) => {
						if (event.key === 'Escape') {
							event.preventDefault();
							createMenu.hidePopover();
							createTrigger.focus();
						}
					}}
				>
					<button
						onclick={() => {
							createMenu.hidePopover();
							onnew();
						}}
						><SquarePen size={17} /><span
							>New direct message<small>Say hello to one person</small></span
						></button
					>
					<button
						onclick={() => {
							createMenu.hidePopover();
							onnewgroup();
						}}
						><Users size={17} /><span>New group<small>A private conversation together</small></span
						></button
					>
				</div>
				<div
					class="conversation-menu"
					popover="manual"
					bind:this={actionMenu}
					role="menu"
					tabindex="-1"
					aria-label="Conversation actions"
					ontoggle={() => (actionOpen = actionMenu.matches(':popover-open'))}
					onkeydown={(event) => {
						if (event.key === 'Escape') {
							event.preventDefault();
							actionMenu.hidePopover();
							actionOpen = false;
							actionTrigger?.focus();
						}
					}}
				>
					{#if actionItem}<button role="menuitem" onclick={() => conversationAction('pin')}
							><Pin size={15} />{actionItem.pinned
								? 'Unpin conversation'
								: 'Pin conversation'}</button
						>
						<button role="menuitem" onclick={() => conversationAction('unread')}
							><CircleDot size={15} />Mark as unread</button
						>
						<button
							class="delete-action"
							role="menuitem"
							onclick={() => conversationAction('delete')}
							><Trash2 size={15} />Delete conversation</button
						>{/if}
				</div>
			</div>
			<label class="search"
				><Search size={16} /><input
					bind:this={searchInput}
					aria-label="Find a conversation"
					placeholder="Find someone…"
					bind:value={query}
				/>{#if query}<button
						class="clear"
						aria-label="Clear conversation search"
						onclick={() => (query = '')}><X size={14} /></button
					>{/if}</label
			>
			<div class="conversation-list" aria-busy={loading}>
				{#if loading && !conversations.length}<p class="list-status" role="status">
						Loading conversations…
					</p>
				{:else if error}<div class="list-status" role="alert">{error}</div>
				{:else}
					{#each matching as item (item.id)}
						<div
							class="conversation"
							class:chosen={selected?.id === item.id}
							role="group"
							aria-label={item.other_name + ' conversation'}
							oncontextmenu={(event) => {
								actionTrigger =
									event.currentTarget.querySelector<HTMLButtonElement>('.conversation-actions')!;
								openActions(event, item);
							}}
						>
							<button
								class="conversation-select"
								aria-current={selected?.id === item.id ? 'true' : undefined}
								onclick={() => void choose(item)}
							>
								<span class="avatar" aria-hidden="true">{initials(item.other_name)}</span><span
									class="person"
									><strong
										>{item.other_name}{#if item.pinned}
											<Pin class="pinned-indicator" size={11} fill="currentColor" />{/if}</strong
									><span
										>{item.kind === 'group'
											? `${item.member_count} people`
											: 'Direct conversation'}</span
									></span
								><span class="conversation-status"
									><time datetime={item.updated_at}>{date(item.updated_at)}</time
									>{#if item.unread_count}<span
											class="unread-badge"
											aria-label={`${item.unread_count} unread ${item.unread_count === 1 ? 'message' : 'messages'}`}
											>{item.unread_count > 99 ? '99+' : item.unread_count}</span
										>{/if}</span
								>
							</button><button
								class="conversation-actions"
								aria-label={'Actions for ' + item.other_name}
								aria-haspopup="menu"
								onclick={(event) => {
									actionTrigger = event.currentTarget;
									openActions(event, item);
								}}><MoreHorizontal size={17} /></button
							>
						</div>
					{:else}<div class="list-status">
							<p>
								{query.trim() ? 'No conversations found.' : 'Your conversations will appear here.'}
							</p>
							{#if !query.trim()}<button class="text-button" onclick={onnew}
									>Say hello to someone <ArrowUpRight size={14} /></button
								>{/if}
						</div>{/each}
				{/if}
			</div>
		</section>
		<section
			class="reading-pane"
			bind:this={readingPane}
			tabindex="-1"
			aria-label={composing
				? 'New conversation'
				: selected
					? 'Conversation with ' + selected.other_name
					: 'Conversation'}
		>
			{#if composing && composeView}
				{@render composeView()}
			{:else if selected}
				<button class="mobile-back" onclick={() => void choose(null)}
					><ArrowLeft size={16} /> All messages</button
				>
				{#key selected.id}{@render conversationView(selected)}{/key}
			{:else}
				<div class="empty-conversation">
					<span class="empty-mark"><MessagesSquare size={28} strokeWidth={1.25} /></span>

					<h3>A conversation starts<br />with a little hello.</h3>
					<p>Pick a conversation, or reach out<br />to someone in your communities.</p>
					<button class="start-button" onclick={onnew}
						><SquarePen size={16} /> Start a conversation</button
					>
				</div>
			{/if}
		</section>
	</div>
</section>

<style>
	.home-copy {
		display: grid;
		gap: 3px;
	}
	.home-copy small {
		font-weight: 400;
	}
	.inbox-mark {
		position: relative;
	}
	.icon-unread {
		position: absolute;
		top: -5px;
		right: -5px;
		min-width: 17px;
		height: 17px;
		border-radius: 20px;
		padding-inline: 4px;
		display: grid;
		place-items: center;
		background: #0868d9;
		color: white;
		font-size: 10px;
		font-weight: 600;
	}
	.conversation-status {
		display: flex;
		flex-direction: column;
		align-items: flex-end;
		gap: 8px;
	}
	.unread-badge {
		min-width: 20px;
		height: 20px;
		padding-inline: 5px;
		border-radius: 20px;
		display: grid;
		place-items: center;
		background: #0868d9;
		color: white;
		font-size: 10px;
		font-weight: 600;
	}
	.create-trigger {
		display: grid;
		place-items: center;
		width: 36px;
		height: 36px;
		background: var(--panel);
		color: var(--ink);
		border: 1px solid var(--line);
		border-radius: 10px;
	}
	.create-menu {
		position: fixed;
		inset: auto;
		margin: 0;
		width: min(270px, calc(100vw - 24px));
		padding: 6px;
		border: 1px solid var(--line);
		border-radius: 14px;
		background: var(--panel);
		color: var(--ink);
		box-shadow: 0 12px 40px #18201524;
	}
	.create-menu button {
		display: flex;
		align-items: center;
		gap: 12px;
		width: 100%;
		min-height: 64px;
		padding: 12px;
		border: 0;
		border-radius: 9px;
		background: transparent;
		color: inherit;
		text-align: left;
		font-size: 13px;
	}
	.create-menu small {
		display: block;
		margin-top: 4px;
		color: var(--muted);
		font-size: 11px;
	}
	@media (hover: hover) and (pointer: fine) {
		.create-menu button:hover,
		.create-trigger:hover {
			background: var(--well);
		}
	}

	.inbox-home {
		display: flex;
		align-items: center;
		gap: 12px;
		font: inherit;
		font-weight: inherit;
		letter-spacing: inherit;
		color: inherit;
		background: transparent;
		border: 0;
		padding: 4px 0;
		border-radius: 4px;
		text-align: left;
	}
	.inbox {
		--panel: #fff;
		--side: #f7f7f4;
		--well: #f0f0eb;
		--ink: #292923;
		--muted: #717169;
		--line: #e8e8e1;
		--accent: #555b45;
		--accent-text: #555b45;
		--control-primary: #33382c;
		font-family: Inter, ui-sans-serif, system-ui, sans-serif;
		color: var(--ink);
		background: var(--panel);
		margin: 0;
		padding: 0;
		width: 100%;
		max-width: none;
		height: 100%;
		max-height: none;
		border: 0;
		border-radius: 0;
		overflow: hidden;
	}
	:global([data-theme='dark']) .inbox {
		--panel: #252621;
		--side: #20211d;
		--well: #30322b;
		--ink: #eeefe7;
		--muted: #b0b2a5;
		--line: #3b3d33;
		--accent: #b5bfa2;
		color-scheme: dark;
	}

	.inbox {
		display: flex;
		flex-direction: column;
	}
	.inbox-heading,
	.title-group,
	.list-heading {
		display: flex;
		align-items: center;
	}
	.inbox-heading {
		flex: none;
		justify-content: space-between;
		padding: 20px 24px;
		border-bottom: 1px solid var(--line);
	}
	.header-actions {
		display: flex;
		align-items: center;
		gap: 8px;
	}
	.theme-toggle {
		display: inline-flex;
		align-items: center;
		gap: 7px;
		min-height: 40px;
		padding: 0 11px;
		border: 1px solid var(--line);
		border-radius: 10px;
		background: transparent;
		color: var(--ink);
		font-size: 12px;
	}
	.title-group {
		gap: 12px;
	}
	.inbox-mark {
		display: grid;
		place-items: center;
		width: 40px;
		height: 40px;
		border: 1px solid var(--line);
		border-radius: 13px;
	}
	h1 {
		margin: 0;
		font-size: 17px;
		font-weight: 600;
		letter-spacing: -0.03em;
	}
	.home-copy small {
		margin: 3px 0 0;
		font-size: 12px;
		color: var(--muted);
	}
	button,
	input {
		font: inherit;
	}
	button {
		cursor: pointer;
		touch-action: manipulation;
		user-select: none;
	}
	button:focus-visible,
	input:focus-visible {
		outline: 2px solid var(--ink);
		outline-offset: 3px;
	}
	.back-button {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		gap: 8px;
		padding: 10px 12px;
		border: 1px solid var(--line);
		border-radius: 10px;
		background: transparent;
		color: var(--ink);
		font-size: 12px;
		min-height: 40px;
	}
	.back-button span {
		max-width: min(42vw, 220px);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.inbox-layout {
		display: grid;
		grid-template-columns: 300px minmax(0, 1fr);
		flex: 1;
		min-height: 0;
	}
	.conversation-pane {
		display: flex;
		flex-direction: column;
		min-height: 0;
		min-width: 0;
		background: var(--side);
		border-right: 1px solid var(--line);
		padding: 22px 12px 16px;
	}
	.list-heading {
		justify-content: space-between;
		gap: 8px;
		margin: 0 10px 16px;
	}
	.list-heading h3 {
		font-size: 12px;
		font-weight: 550;
		margin: 0;
		color: var(--muted);
	}
	.search {
		display: flex;
		align-items: center;
		gap: 8px;
		background: var(--panel);
		border: 1px solid var(--line);
		border-radius: 9px;
		margin: 0 8px 18px;
		padding: 0 10px;
		color: var(--muted);
	}
	.search input {
		width: 100%;
		min-width: 0;
		height: 40px;
		border: 0;
		background: transparent;
		color: var(--ink);
		font-size: 13px;
	}
	.clear {
		display: grid;
		place-items: center;
		flex: none;
		width: 26px;
		height: 32px;
		padding: 0;
		background: transparent;
		color: var(--muted);
		border: 0;
	}
	.conversation-list {
		flex: 1;
		min-height: 0;
		overflow-y: auto;
		overscroll-behavior: contain;
	}
	.conversation {
		display: flex;
		align-items: center;
		gap: 10px;
		text-align: left;
		width: 100%;
		border: 1px solid transparent;
		padding: 13px 10px;
		border-radius: 11px;
		background: transparent;
		color: var(--ink);
		position: relative;
	}
	.conversation-select {
		display: flex;
		align-items: center;
		gap: 10px;
		flex: 1;
		min-width: 0;
		padding: 0;
		border: 0;
		background: transparent;
		color: inherit;
		text-align: left;
	}
	.conversation-actions {
		flex: none;
		display: grid;
		place-items: center;
		width: 30px;
		height: 30px;
		margin-left: auto;
		border: 0;
		border-radius: 8px;
		background: transparent;
		color: var(--muted);
		opacity: 0;
	}
	.conversation:focus-within .conversation-actions,
	.conversation:hover .conversation-actions {
		opacity: 1;
	}
	.conversation-menu {
		position: fixed;
		inset: auto;
		margin: 0;
		width: 205px;
		padding: 5px;
		border: 1px solid var(--line);
		border-radius: 12px;
		background: var(--panel);
		color: var(--ink);
		box-shadow: 0 14px 42px #1820152e;
	}
	.conversation-menu button {
		display: flex;
		align-items: center;
		gap: 10px;
		width: 100%;
		min-height: 39px;
		padding: 0 10px;
		border: 0;
		border-radius: 8px;
		background: transparent;
		color: inherit;
		text-align: left;
		font-size: 12px;
	}
	.conversation-menu .delete-action {
		color: #c44343;
	}
	:global([data-theme='dark']) .conversation-menu .delete-action {
		color: #ff8888;
	}
	.conversation.chosen {
		background: var(--panel);
		border-color: var(--line);
		box-shadow: 0 2px 4px #24271d04;
	}
	.avatar {
		display: grid;
		place-items: center;
		flex: none;
		width: 38px;
		height: 38px;
		border-radius: 50%;
		background: #e7eadf;
		color: #525947;
		font-size: 12px;
		font-weight: 550;
	}
	.person {
		display: grid;
		gap: 4px;
		min-width: 0;
		flex: 1;
	}
	.person strong {
		font-weight: 550;
		font-size: 13px;
		overflow-wrap: anywhere;
	}
	.person strong :global(.pinned-indicator) {
		vertical-align: -1px;
		color: var(--muted);
	}
	.person > span,
	time {
		font-size: 11px;
		color: var(--muted);
	}
	time {
		flex: none;
		align-self: flex-start;
		margin-top: 4px;
	}
	.list-status {
		padding: 24px 14px;
		font-size: 13px;
		color: var(--muted);
		line-height: 1.6;
	}
	.list-status p {
		margin: 0 0 14px;
	}
	.text-button {
		display: inline-flex;
		align-items: center;
		gap: 4px;
		color: var(--ink);
		background: transparent;
		border: 0;
		padding: 0;
		font-size: 12px;
	}
	.reading-pane {
		outline: none;
		display: flex;
		flex-direction: column;
		min-width: 0;
		min-height: 0;
		position: relative;
	}
	.empty-conversation {
		margin: auto;
		padding: 32px 20px;
		text-align: center;
	}
	.empty-mark {
		margin-bottom: 24px;
		display: inline-grid;
		place-items: center;
		width: 72px;
		height: 72px;
		background: var(--side);
		border: 1px solid var(--line);
		border-radius: 24px;
		color: #788168;
	}
	.empty-conversation h3 {
		font-size: clamp(23px, 2.5vw, 30px);
		font-weight: 500;
		line-height: 1.25;
		letter-spacing: -0.04em;
		margin: 0;
	}
	.empty-conversation > p:last-of-type {
		color: var(--muted);
		font-size: 13px;
		line-height: 1.7;
		margin: 16px 0 24px;
	}
	.start-button {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		gap: 8px;
		min-height: 42px;
		padding: 10px 15px;
		border: 1px solid var(--line);
		border-radius: 10px;
		background: var(--panel);
		color: var(--ink);
		font-size: 12px;
		font-weight: 550;
		box-shadow: 0 2px 3px #15191004;
	}
	.mobile-back {
		display: none;
	}
	@media (hover: hover) and (pointer: fine) {
		.conversation:not(.chosen):hover {
			background: var(--well);
		}
		.conversation-actions:hover,
		.theme-toggle:hover {
			background: var(--well);
		}
		.start-button:hover {
			border-color: var(--muted);
		}
	}
	/* The screen appears as one surface; conversation switching stays immediate. */
	@media (prefers-reduced-motion: no-preference) {
		.inbox {
			animation: inbox-arrive 220ms var(--ease-out);
		}
		.inbox,
		.inbox :where(button, input, .conversation-pane, .reading-pane, .inbox-heading) {
			transition:
				background-color 220ms ease,
				border-color 220ms ease,
				color 220ms ease;
		}
		@keyframes inbox-arrive {
			from {
				opacity: 0;
				transform: translateY(6px);
			}
			to {
				opacity: 1;
				transform: translateY(0);
			}
		}
		.back-button,
		.start-button {
			transition: transform 120ms var(--ease-out);
		}
		.back-button:active:not(:focus-visible),
		.start-button:active:not(:focus-visible) {
			transform: scale(0.97);
		}
	}

	@media (max-width: 700px) {
		.inbox {
			width: 100%;
			height: 100%;
			border-radius: 0;
		}
		.inbox-heading {
			padding: 16px;
		}
		.theme-toggle span {
			display: none;
		}
		.theme-toggle {
			width: 40px;
			justify-content: center;
			padding: 0;
		}
		.home-copy small {
			display: none;
		}
		.inbox-layout {
			grid-template-columns: minmax(0, 1fr);
		}
		.conversation-pane {
			border-right: 0;
			padding-bottom: max(16px, env(safe-area-inset-bottom));
		}
		.reading-pane {
			outline: none;
			display: none;
		}
		.has-conversation .conversation-pane {
			display: none;
		}
		.has-conversation .reading-pane {
			display: flex;
		}
		.mobile-back {
			display: inline-flex;
			align-items: center;
			gap: 8px;
			flex: none;
			min-height: 40px;
			padding: 10px 16px;
			color: var(--muted);
			background: transparent;
			border: 0;
			border-bottom: 1px solid var(--line);
			font-size: 12px;
		}
		.search input {
			font-size: 16px;
		}
	}
</style>
