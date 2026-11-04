<script lang="ts">
	import { chatControls } from '$lib/chatControls';
	import { communityRequest, type Poll } from './communities';
	let { poll, url, onvote }: { poll: Poll; url: string; onvote: (poll: Poll) => void } = $props();
	let error = $state(''),
		busy = $state(false);
	async function vote(choice: number) {
		busy = true;
		try {
			onvote(await communityRequest<Poll>(url, 'PUT', { choice }));
			error = '';
		} catch (e) {
			error = e instanceof Error ? e.message : 'Vote failed';
		} finally {
			busy = false;
		}
	}
</script>

<div class="ballot" role="group" aria-label="Poll options">
	{#each poll.options as option, i (option)}<button
			class={chatControls.ghost}
			disabled={busy}
			aria-pressed={poll.mine === i}
			onclick={() => void vote(i)}>{poll.mine === i ? '✓ ' : ''}{option} · {poll.counts[i]}</button
		>{/each}
</div>
{#if error}<span role="alert">{error}</span>{/if}

<style>
	.ballot {
		display: grid;
		gap: 5px;
		max-width: 380px;
		margin-block: 8px;
	}
	.ballot button {
		min-height: 34px;
		text-align: left;
		padding: 6px 12px;
		border-radius: 7px;
		border: 1px solid var(--line);
		background: var(--well);
		color: var(--ink);
		overflow-wrap: anywhere;
	}
	.ballot button:hover,
	.ballot button[aria-pressed='true'] {
		border-color: var(--accent);
	}
</style>
