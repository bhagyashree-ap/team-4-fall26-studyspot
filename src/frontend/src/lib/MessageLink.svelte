<script lang="ts">
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import Link2 from '@lucide/svelte/icons/link-2';
	import Check from '@lucide/svelte/icons/check';
	import { messageLink } from './chatLinks';
	let { id, label = false }: { id: number; label?: boolean } = $props();
	let fallback = $state(''),
		copied = $state(false);
	async function copy() {
		const url = messageLink(location.href, id);
		try {
			await navigator.clipboard.writeText(url);
			copied = true;
		} catch {
			fallback = url;
		}
	}
</script>

{#snippet icon()}{#if copied}<Check size={16} />{:else}<Link2 size={16} />{/if}{/snippet}
{#if label}
	<button
		class="copy-row"
		title="Copy link to message"
		onclick={copy}
		aria-label={copied ? 'Link copied' : 'Copy link to message'}
		>{@render icon()}<span>{copied ? 'Link copied' : 'Copy link'}</span></button
	>
{:else}
	<Button
		variant="ghost"
		size="icon-sm"
		title="Copy link to message"
		onclick={copy}
		aria-label={copied ? 'Link copied' : 'Copy link to message'}>{@render icon()}</Button
	>
{/if}
{#if fallback}<Input
		aria-label="Message link"
		readonly
		value={fallback}
		onclick={(e) => e.currentTarget.select()}
	/>{/if}

<style>
	.copy-row {
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
	.copy-row :global(svg) {
		color: var(--muted);
	}
	.copy-row:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}
	@media (hover: hover) and (pointer: fine) {
		.copy-row:hover {
			background: var(--well);
		}
	}
</style>
