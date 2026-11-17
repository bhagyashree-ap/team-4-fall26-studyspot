<script lang="ts">
	import { onDestroy } from 'svelte';
	import { boardError } from '$lib/board';
	let {
		target,
		limit,
		onsubmit
	}: {
		target: 'post' | 'comment';
		limit: number;
		onsubmit: (reason: string) => Promise<unknown>;
	} = $props();
	const id = $props.id();
	let open = $state(false);
	let reason = $state('');
	let saving = $state(false);
	let sent = $state(false);
	let error = $state('');
	let alive = true;
	onDestroy(() => (alive = false));

	async function submit(event: SubmitEvent) {
		event.preventDefault();
		if (saving || !reason.trim()) return;
		saving = true;
		error = '';
		try {
			await onsubmit(reason);
			if (alive) {
				sent = true;
				open = false;
				reason = '';
			}
		} catch (cause) {
			if (alive) error = `${boardError(cause)} Your reason is still here. Please try again.`;
		} finally {
			if (alive) saving = false;
		}
	}
</script>

<div class="board-report">
	{#if sent}
		<p class="board-help" role="status">Report received. Only staff can review reports.</p>
	{:else}
		<button type="button" aria-expanded={open} aria-controls={id} onclick={() => (open = !open)}>
			Report {target}
		</button>
		{#if open}
			<form {id} class="board-report-form" aria-label={`Report ${target}`} onsubmit={submit}>
				<div class="board-field">
					<label for={`${id}-reason`}>Reason for reporting this {target}</label>
					<textarea
						id={`${id}-reason`}
						bind:value={reason}
						maxlength={limit}
						rows="3"
						required
						disabled={saving}></textarea>
					<p class="board-help">Your report is private and visible only to staff.</p>
				</div>
				{#if error}<p class="board-error" role="alert">{error}</p>{/if}
				<div class="board-actions">
					<button type="submit" disabled={saving || !reason.trim()}
						>{saving ? 'Sending report…' : 'Send report'}</button
					>
					<button type="button" disabled={saving} onclick={() => (open = false)}
						>Cancel report</button
					>
				</div>
			</form>
		{/if}
	{/if}
</div>
