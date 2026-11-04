<script lang="ts">
	import { chatControls } from '$lib/chatControls';
	import { Input } from '$lib/components/ui/input';
	import { NativeSelect } from '$lib/components/ui/native-select';
	import Smile from '@lucide/svelte/icons/smile';
	import SmilePlus from '@lucide/svelte/icons/smile-plus';
	import Search from '@lucide/svelte/icons/search';
	import X from '@lucide/svelte/icons/x';
	import { tick } from 'svelte';
	let { onpick, reaction = false }: { onpick: (value: string) => void; reaction?: boolean } =
		$props();
	let panel: HTMLDivElement, trigger: HTMLButtonElement;
	let input = $state<HTMLInputElement>();
	let catalog = $state.raw<Record<string, string[][]>>({}),
		query = $state(''),
		group = $state('Smileys & Emotion'),
		limit = $state(80);
	let term = $derived(query.trim().toLowerCase());
	let found = $derived(
		term
			? Object.values(catalog)
					.flat()
					.filter(([glyph, name]) => glyph === term || name.toLowerCase().includes(term))
			: (catalog[group] ?? [])
	);
	async function open() {
		query = '';
		limit = 80;
		const rect = trigger.getBoundingClientRect();
		panel.style.left = Math.max(8, Math.min(rect.right - 320, innerWidth - 328)) + 'px';
		panel.style.top =
			Math.max(8, Math.min(rect.top > 360 ? rect.top - 352 : rect.bottom + 6, innerHeight - 352)) +
			'px';
		panel.showPopover();
		input?.focus();
		catalog = (await import('./emoji/catalog.json')).default;
	}
	function select(glyph: string) {
		onpick(glyph);
		panel.hidePopover();
		trigger.focus();
	}
	async function changeGroup(value: string) {
		group = value;
		limit = 80;
		query = '';
		await tick();
		panel.querySelector('.grid')?.scrollTo(0, 0);
	}
</script>

<button
	class="chat-icon {chatControls.icon}"
	bind:this={trigger}
	type="button"
	aria-label={reaction ? 'Add reaction' : 'Choose emoji'}
	title={reaction ? 'Add reaction' : 'Choose emoji'}
	onclick={open}
	>{#if reaction}<SmilePlus size={19} />{:else}<Smile size={21} />{/if}</button
>
<div class="emoji-panel" bind:this={panel} popover="auto" role="dialog" aria-label="Emoji picker">
	<header>
		<strong>Emoji</strong><button
			class="chat-icon {chatControls.icon}"
			aria-label="Close emoji picker"
			onclick={() => panel.hidePopover()}><X size={16} /></button
		>
	</header>
	<label class="search"
		><Search size={16} /><Input
			bind:ref={input}
			aria-label="Search all emoji"
			placeholder="Search all emoji"
			bind:value={query}
			oninput={() => (limit = 80)}
		/></label
	>
	<NativeSelect
		aria-label="Emoji category"
		value={group}
		onchange={(e) => void changeGroup(e.currentTarget.value)}
		>{#each Object.keys(catalog) as category (category)}<option>{category}</option
			>{/each}</NativeSelect
	>
	<div class="grid">
		{#each found.slice(0, limit) as [glyph, name] (glyph)}<button
				class={chatControls.icon}
				type="button"
				title={name}
				aria-label={name}
				onclick={() => select(glyph)}>{glyph}</button
			>{:else}<small>{Object.keys(catalog).length ? 'No matching emoji' : 'Loading…'}</small>{/each}
		{#if found.length > limit}<button
				class="more {chatControls.ghost}"
				onclick={() => (limit += 120)}>Show more</button
			>{/if}
	</div>
</div>

<style>
	.emoji-panel {
		position: fixed;
		inset: auto;
		margin: 0;
		width: min(320px, calc(100vw - 16px));
		height: min(344px, calc(100dvh - 16px));
		border: 1px solid var(--line);
		border-radius: 14px;
		background: var(--panel);
		color: var(--ink);
		box-shadow: 0 10px 48px #0003;
		padding: 12px;
	}
	.emoji-panel:popover-open {
		display: flex;
		flex-direction: column;
		gap: 8px;
	}
	header,
	.search {
		display: flex;
		align-items: center;
		gap: 8px;
	}
	header {
		justify-content: space-between;
	}
	.search {
		padding: 7px 9px;
		border-radius: 6px;
		background: var(--well);
	}
	.emoji-panel :global(input) {
		min-width: 0;
		background: none;
		outline: none;
		border: 0;
		color: inherit;
	}
	.emoji-panel :global(select) {
		background: var(--panel);
		color: var(--muted);
		font: inherit;
		font-size: 12px;
	}
	.grid {
		display: grid;
		grid-template-columns: repeat(8, 1fr);
		align-content: start;
		overflow: auto;
		min-height: 0;
	}
	.grid button {
		border: 0;
		background: transparent;
		color: inherit;
		font-size: 23px;
		border-radius: 6px;
		line-height: 1.45;
	}
	.grid button:hover {
		background: var(--hover);
	}
	.grid .more,
	.grid small {
		grid-column: 1/-1;
		font-size: 13px;
		padding: 6px;
	}
</style>
