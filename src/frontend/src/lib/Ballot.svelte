<script lang="ts">
	import { chatControls } from '$lib/chatControls';
	import { communityRequest, type Poll } from './communities';
	let { poll, url, onvote }: { poll: Poll; url: string; onvote: (poll: Poll) => void } = $props();
	let error = $state(''),
		busy = $state(false);
	const totalVotes = $derived(poll.counts.reduce((sum, count) => sum + count, 0));
	function percentage(count: number) {
		return totalVotes ? Math.round((count / totalVotes) * 100) : 0;
	}
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
			onclick={() => void vote(i)}
		>
			<span class="option-label"
				><span>{poll.mine === i ? '✓ ' : ''}{option}</span><span>{poll.counts[i]}</span></span
			><span
				class="vote-track"
				role="progressbar"
				aria-label={`${option}: ${percentage(poll.counts[i])}%`}
				aria-valuemin="0"
				aria-valuemax="100"
				aria-valuenow={percentage(poll.counts[i])}
				><span class="vote-fill" style={`width: ${percentage(poll.counts[i])}%`}></span></span
			>
		</button>{/each}
	<p class="vote-summary">{totalVotes} {totalVotes === 1 ? 'vote' : 'votes'}</p>
</div>
{#if error}<span role="alert">{error}</span>{/if}

<style>
	.ballot {
		display: grid;
		gap: 7px;
		max-width: 380px;
		margin-block: 8px;
	}
	.ballot button {
		min-height: 58px;
		display: grid;
		gap: 8px;
		text-align: left;
		padding: 9px 11px;
		border-radius: 10px;
		border: 1px solid var(--line);
		background: var(--well);
		color: var(--ink);
		overflow-wrap: anywhere;
	}
	.option-label {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 12px;
		font-size: 12px;
		line-height: 1.35;
	}
	.option-label > span:first-child {
		min-width: 0;
	}
	.option-label > span:last-child {
		color: var(--muted);
		font-variant-numeric: tabular-nums;
	}
	.vote-track {
		display: block;
		width: 100%;
		height: 6px;
		overflow: hidden;
		border-radius: 8px;
		background: var(--poll-track, #46464a);
	}
	.vote-fill {
		display: block;
		height: 100%;
		border-radius: inherit;
		background: #25d366;
	}
	.vote-summary {
		margin: 0 2px;
		color: var(--muted);
		font-size: 10px;
	}
	.ballot button:hover,
	.ballot button[aria-pressed='true'] {
		border-color: #25d366;
	}
	@media (prefers-reduced-motion: no-preference) {
		.vote-fill {
			transition: width 360ms cubic-bezier(0.22, 1, 0.36, 1);
		}
	}
</style>
