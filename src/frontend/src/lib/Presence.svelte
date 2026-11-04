<script lang="ts">
	import { NativeSelect } from '$lib/components/ui/native-select';
	import { onMount } from 'svelte';
	import { communityRequest } from './communities';
	let {
		url,
		onread,
		ontyping,
		expanded = false
	}: {
		expanded?: boolean;
		url: string;
		onread?: (id: number) => void;
		ontyping: (names: string[]) => void;
	} = $props();
	const options = [
		{ value: 'all', label: 'All messages', description: 'Show every new message in your inbox.' },
		{ value: 'mentions', label: 'Mentions only', description: 'Show messages that mention you.' },
		{ value: 'muted', label: 'Muted', description: 'Keep this conversation out of your inbox.' }
	];
	let saving = $state(false);
	let version = 0;
	let mode = $state('all'),
		notice = $state('');
	async function setMode(alerts: string) {
		if (saving) return;
		saving = true;
		version++;
		try {
			await communityRequest(url.replace(/presence$/, 'alerts'), 'PUT', { alerts });
			mode = alerts;
			notice = '';
		} catch (e) {
			notice = e instanceof Error ? e.message : 'Save failed';
		} finally {
			saving = false;
			version++;
		}
	}
	let lastSignal = 0,
		lastActive = 0;
	export function typing() {
		if (Date.now() - lastSignal < 3000) return;
		lastSignal = Date.now();
		void signal({ typing: true });
	}
	async function signal(body: object) {
		try {
			await communityRequest(url, 'POST', body);
		} catch {
			ontyping([]);
		}
	}
	onMount(() => {
		let busy = false,
			closed = false;
		async function poll() {
			if (document.hidden || busy) return;
			busy = true;
			try {
				if (Date.now() - lastActive > 30000) {
					lastActive = Date.now();
					await signal({});
				}
				const polledVersion = version;
				const data = await communityRequest<{
					typing: string[];
					alerts: string;
					last_read: number;
				}>(url);
				if (!closed) {
					ontyping(data.typing);
					if (!saving && version === polledVersion) mode = data.alerts;
					onread?.(data.last_read);
				}
			} catch {
				ontyping([]);
			} finally {
				busy = false;
			}
		}
		void poll();
		const timer = setInterval(poll, 3000);
		return () => {
			closed = true;
			clearInterval(timer);
		};
	});
</script>

{#if expanded}
	<fieldset class="notification-options" disabled={saving}>
		<legend>Inbox notifications</legend>
		{#each options as option (option.value)}
			<label
				><input
					type="radio"
					name="dm-alerts"
					value={option.value}
					checked={mode === option.value}
					onchange={() => void setMode(option.value)}
				/><span><b>{option.label}</b><small>{option.description}</small></span></label
			>
		{/each}
	</fieldset>
{:else}
	<label
		>Notifications<NativeSelect
			aria-label="Notifications"
			disabled={saving}
			value={mode}
			onchange={(e) => void setMode(e.currentTarget.value)}
			>{#each options as option (option.value)}<option value={option.value}>{option.label}</option
				>{/each}</NativeSelect
		></label
	>
{/if}
{#if notice}<span role="alert">{notice}</span>{/if}

<style>
	.notification-options {
		display: grid;
		gap: 5px;
		max-width: 440px;
	}
	legend {
		color: var(--muted);
		font-size: 12px;
		margin-bottom: 8px;
	}
	.notification-options label {
		display: flex;
		align-items: center;
		gap: 12px;
		padding: 9px 12px;
		border: 1px solid var(--line);
		border-radius: 9px;
		background: var(--panel);
		cursor: pointer;
	}
	.notification-options label:has(:checked) {
		border-color: var(--accent);
	}
	input {
		accent-color: var(--accent);
	}
	b,
	small {
		display: block;
	}
	small {
		font-size: 12px;
		color: var(--muted);
	}
</style>
