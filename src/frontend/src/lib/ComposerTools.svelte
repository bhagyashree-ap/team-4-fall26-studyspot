<script lang="ts">
	import { chatControls } from '$lib/chatControls';
	import Plus from '@lucide/svelte/icons/plus';
	import Paperclip from '@lucide/svelte/icons/paperclip';
	import CheckCheck from '@lucide/svelte/icons/check-check';
	import Presence from './Presence.svelte';
	import MentionPicker from './MentionPicker.svelte';
	import PollComposer from './PollComposer.svelte';
	let {
		room,
		names,
		groups = false,
		withPresence = true,
		files = $bindable(),
		onmention,
		onread,
		onmark,
		onsent
	}: {
		room: string;
		names: string[];
		groups?: boolean;
		withPresence?: boolean;
		files?: FileList;
		onmention: (s: string) => void;
		onread: (id: number) => void;
		onmark: () => void;
		onsent: () => void;
	} = $props();
	let typingNames = $state<string[]>([]);
	let presence = $state<Presence>(),
		menu: HTMLDivElement,
		trigger: HTMLButtonElement;
	export function typing() {
		presence?.typing();
	}
	function open() {
		const r = trigger.getBoundingClientRect();
		menu.style.left = Math.min(r.left, innerWidth - 258) + 'px';
		menu.style.bottom = innerHeight - r.top + 6 + 'px';
		menu.showPopover();
	}
</script>

<button
	type="button"
	class="chat-icon {chatControls.icon}"
	aria-label="More message options"
	title="More message options"
	bind:this={trigger}
	onclick={open}><Plus size={22} /></button
>
<div popover="auto" class="tools" bind:this={menu}>
	<label class="attach"
		><Paperclip size={16} />Attach a file <small>2 MiB</small><input
			aria-label="Attach file"
			type="file"
			bind:files
			onchange={() => menu.hidePopover()}
		/></label
	>
	<PollComposer
		url={room + '/messages'}
		onsent={() => {
			menu.hidePopover();
			onsent();
		}}
	/>
	<MentionPicker
		{names}
		{groups}
		onpick={(s) => {
			onmention(s);
			menu.hidePopover();
		}}
	/>
	{#if withPresence}<Presence
			url={room + '/presence'}
			bind:this={presence}
			{onread}
			ontyping={(items) => (typingNames = items)}
		/>{/if}
	<button
		class={chatControls.ghost}
		type="button"
		onclick={() => {
			onmark();
			menu.hidePopover();
		}}><CheckCheck size={16} />Mark as read</button
	>
</div>
{#if typingNames.length}<small class="typing" aria-live="polite"
		>{typingNames.join(', ')} {typingNames.length === 1 ? 'is' : 'are'} typing…</small
	>{/if}

<style>
	.tools {
		position: fixed;
		inset: auto;
		padding: 7px;
		margin: 0;
		border: 1px solid var(--line);
		border-radius: 10px;
		background: var(--panel);
		color: var(--ink);
		box-shadow: 0 6px 26px #0003;
		width: 250px;
		max-height: 60vh;
		overflow: auto;
		font-size: 13px;
	}
	.tools :global(label),
	.tools :global(summary),
	.tools > button {
		display: flex;
		align-items: center;
		gap: 8px;
		padding: 8px;
		width: 100%;
		border-radius: 5px;
		cursor: pointer;
	}
	.tools :global(label:hover),
	.tools :global(summary:hover),
	.tools > button:hover {
		background: var(--hover);
	}
	.tools :global(select) {
		margin-left: auto;
		min-width: 0;
		background: var(--well);
		color: var(--ink);
		max-width: 128px;
	}
	.attach {
		position: relative;
	}
	.attach small {
		margin-left: auto;
		color: var(--muted);
	}
	.attach input {
		position: absolute;
		inset: 0;
		opacity: 0;
		width: 100%;
		cursor: pointer;
	}
	.typing {
		position: absolute;
		bottom: -18px;
		left: 10px;
		color: var(--muted);
		font-size: 11px;
	}
</style>
