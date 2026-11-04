<script lang="ts">
	import { Input } from '$lib/components/ui/input';
	import { Button } from '$lib/components/ui/button';
	import { SvelteURLSearchParams } from 'svelte/reactivity';
	import { communityRequest } from './communities';
	let {
		url,
		onresults,
		onerror
	}: {
		url: string;
		onresults: (
			items: { id: number; created_at: string; author_name: string; content: string }[]
		) => void;
		onerror: (message: string) => void;
	} = $props();
	let keyword = $state(''),
		sender = $state(''),
		date = $state('');
	async function search() {
		const params = new SvelteURLSearchParams();
		if (keyword.trim()) params.set('q', keyword.trim());
		if (sender.trim()) params.set('sender', sender.trim());
		if (date) params.set('date', date);
		try {
			const result = await communityRequest<{
				items: { id: number; created_at: string; author_name: string; content: string }[];
			}>(url + '?' + params);
			onresults(result.items);
		} catch (e) {
			onerror(e instanceof Error ? e.message : 'Search failed.');
		}
	}
</script>

<form
	class="message-search"
	aria-label="Message filters"
	onsubmit={(e) => {
		e.preventDefault();
		void search();
	}}
>
	<Input aria-label="Keyword" placeholder="Keyword" minlength={2} bind:value={keyword} />
	<Input aria-label="Sender" placeholder="Exact sender name" bind:value={sender} />
	<Input aria-label="Date (UTC)" type="date" bind:value={date} />
	<Button
		variant="ghost"
		size="sm"
		type="submit"
		disabled={!keyword.trim() && !sender.trim() && !date}>Search</Button
	>
</form>

<style>
	.message-search {
		display: flex;
		align-items: center;
		flex-wrap: wrap;
		gap: 8px;
		padding: 12px 16px;
		background: var(--side);
		border-bottom: 1px solid var(--line);
	}
	.message-search :global(input),
	.message-search :global(button) {
		min-height: 34px;
		padding: 6px 9px;
		border-radius: 7px;
		border: 1px solid var(--line);
		font: inherit;
		font-size: 13px;
		background: var(--panel);
		color: var(--ink);
	}
	.message-search :global(input) {
		flex: 1 1 110px;
		width: 0;
		min-width: 90px;
	}
	.message-search :global(button) {
		background: var(--well);
		font-weight: 600;
	}
	.message-search :global(button:disabled) {
		opacity: 0.55;
	}
</style>
