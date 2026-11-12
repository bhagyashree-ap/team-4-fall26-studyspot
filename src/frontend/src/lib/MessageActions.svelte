<script lang="ts">
	import Ellipsis from '@lucide/svelte/icons/ellipsis';
	import Reply from '@lucide/svelte/icons/reply';
	import Pin from '@lucide/svelte/icons/pin';
	import MessagesSquare from '@lucide/svelte/icons/messages-square';
	import Mail from '@lucide/svelte/icons/mail';
	import Pencil from '@lucide/svelte/icons/pencil';
	import Trash2 from '@lucide/svelte/icons/trash-2';
	import EmojiPicker from './EmojiPicker.svelte';
	import MessageLink from './MessageLink.svelte';
	import type { DirectMessage } from './communities';

	let {
		message,
		onaction,
		onreact
	}: {
		message: DirectMessage;
		onaction: (action: 'reply' | 'pin' | 'thread' | 'unread' | 'edit' | 'delete') => void;
		onreact: (emoji: string) => void;
	} = $props();
	let panel: HTMLDivElement;
	let trigger: HTMLButtonElement;
	let expanded = $state(false);
	let motion = $state(false);
	const id = $props.id();
	$effect(() => {
		if (!expanded) return;
		const dismiss = (event: Event) => {
			if (
				event.target instanceof Node &&
				(panel.contains(event.target) || trigger.contains(event.target))
			)
				return;
			panel.hidePopover();
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

	function open(event: MouseEvent) {
		const contextX = trigger.dataset.contextX;
		const contextY = trigger.dataset.contextY;
		delete trigger.dataset.contextX;
		delete trigger.dataset.contextY;
		const fromContextMenu = contextX !== undefined && contextY !== undefined;
		if (panel.matches(':popover-open') && !fromContextMenu) {
			panel.hidePopover();
			return;
		}
		if (panel.matches(':popover-open')) panel.hidePopover();
		motion = event.detail > 0 || fromContextMenu;
		panel.showPopover();
		const width = panel.offsetWidth;
		const height = panel.offsetHeight;
		if (fromContextMenu) {
			const x = Number(contextX);
			const y = Number(contextY);
			panel.style.left = Math.max(12, Math.min(x, innerWidth - width - 12)) + 'px';
			panel.style.top = Math.max(12, Math.min(y, innerHeight - height - 12)) + 'px';
			panel.style.transformOrigin = 'top left';
		} else {
			const origin = trigger.getBoundingClientRect();
			const above = origin.bottom + height + 12 > innerHeight;
			panel.style.left =
				Math.max(12, Math.min(origin.right - width, innerWidth - width - 12)) + 'px';
			panel.style.top = Math.max(12, above ? origin.top - height - 6 : origin.bottom + 6) + 'px';
			panel.style.transformOrigin = above ? 'bottom right' : 'top right';
		}
		if (!motion || fromContextMenu) panel.querySelector<HTMLButtonElement>('button')?.focus();
	}
	function act(action: Parameters<typeof onaction>[0]) {
		panel.hidePopover();
		trigger.focus();
		onaction(action);
	}
</script>

<button
	class="action-trigger"
	class:expanded
	bind:this={trigger}
	aria-label={'Actions for message from ' + (message.mine ? 'you' : message.author_name)}
	aria-haspopup="dialog"
	aria-expanded={expanded}
	aria-controls={id}
	onclick={open}><Ellipsis size={18} /></button
>
<div
	{id}
	class="message-actions"
	bind:this={panel}
	popover="manual"
	role="dialog"
	tabindex="-1"
	aria-label="Message actions"
	data-motion={motion}
	ontoggle={() => (expanded = panel.matches(':popover-open'))}
	onkeydown={(event) => {
		if (event.key === 'Escape' && (event.target as HTMLElement).closest('[popover]') === panel) {
			event.preventDefault();
			event.stopPropagation();
			panel.hidePopover();
			trigger.focus();
		}
	}}
>
	<div class="quick-reactions" aria-label="Quick reactions">
		{#each ['👍', '❤️', '😂', '🎉', '☕'] as emoji (emoji)}<button
				aria-label={'React with ' + emoji}
				onclick={() => {
					panel.hidePopover();
					trigger.focus();
					onreact(emoji);
				}}>{emoji}</button
			>{/each}
	</div>
	<div class="menu-section">
		<button onclick={() => act('reply')}><Reply size={16} />Reply</button>
		<button onclick={() => act('thread')}><MessagesSquare size={16} />Open thread</button>
		<button onclick={() => act('pin')}
			><Pin size={16} />{message.pinned_at ? 'Unpin message' : 'Pin message'}</button
		>
		<EmojiPicker
			reaction
			label="More reactions"
			onpick={(emoji) => {
				panel.hidePopover();
				onreact(emoji);
			}}
		/>
	</div>
	<div class="menu-section">
		<MessageLink id={message.id} label /><button onclick={() => act('unread')}
			><Mail size={16} />Mark unread</button
		>
	</div>
	{#if message.mine}<div class="menu-section">
			<button onclick={() => act('edit')}><Pencil size={16} />Edit message</button><button
				class="destructive"
				onclick={() => act('delete')}><Trash2 size={16} />Delete message</button
			>
		</div>{/if}
</div>

<style>
	.action-trigger {
		display: inline-grid;
		place-items: center;
		width: 36px;
		height: 36px;
		padding: 0;
		background: transparent;
		border: 0;
		border-radius: 50%;
		color: var(--muted);
		cursor: pointer;
		flex: none;
	}
	.action-trigger.expanded {
		background: var(--well);
		color: var(--ink);
	}
	.action-trigger:focus-visible,
	.message-actions button:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}
	.message-actions {
		position: fixed;
		inset: auto;
		margin: 0;
		width: min(244px, calc(100vw - 24px));
		max-height: calc(100dvh - 24px);
		overflow-y: auto;
		padding: 6px;
		border: 1px solid var(--line);
		border-radius: 16px;
		background: var(--panel);
		color: var(--ink);
		box-shadow:
			0 12px 40px #18201524,
			0 2px 5px #1820150a;
		font-family: inherit;
	}
	.quick-reactions {
		display: flex;
		justify-content: space-between;
		gap: 2px;
		padding: 6px 4px 10px;
	}
	.quick-reactions button {
		display: grid;
		place-items: center;
		width: 38px;
		height: 38px;
		border: 0;
		border-radius: 10px;
		background: var(--side);
		font-size: 21px;
		cursor: pointer;
	}
	.menu-section {
		border-top: 1px solid var(--line);
		padding-top: 5px;
		margin-top: 4px;
	}
	.menu-section > button {
		display: flex;
		align-items: center;
		gap: 10px;
		width: 100%;
		min-height: 40px;
		padding: 10px 12px;
		border: 0;
		border-radius: 8px;
		background: transparent;
		color: var(--ink);
		text-align: left;
		font: inherit;
		font-size: 13px;
		cursor: pointer;
	}
	.menu-section > button :global(svg) {
		color: var(--muted);
	}
	.menu-section > .destructive,
	.menu-section > .destructive :global(svg) {
		color: var(--danger);
	}
	@media (hover: hover) and (pointer: fine) {
		.action-trigger:hover,
		.menu-section > button:hover,
		.quick-reactions button:hover {
			background: var(--well);
		}
	}
	.message-actions[data-motion] {
		animation: none;
	}
	@media (prefers-reduced-motion: no-preference) {
		.message-actions[data-motion='true'] {
			opacity: 0;
			transform: scale(0.96);
			transition:
				opacity 120ms var(--ease-out),
				transform 120ms var(--ease-out),
				display 120ms allow-discrete,
				overlay 120ms allow-discrete;
		}
		.message-actions[data-motion='true']:popover-open {
			opacity: 1;
			transform: scale(1);
			transition-duration: 180ms;
		}
		@starting-style {
			.message-actions[data-motion='true']:popover-open {
				opacity: 0;
				transform: scale(0.96);
			}
		}
		.quick-reactions button {
			transition: transform 120ms var(--ease-out);
		}
		.quick-reactions button:active:not(:focus-visible) {
			transform: scale(0.9);
		}
	}
	@media (pointer: coarse) {
		.action-trigger {
			width: 40px;
			height: 40px;
		}
	}
</style>
