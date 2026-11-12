<script lang="ts">
	import { onMount } from 'svelte';
	import { NativeSelect } from '$lib/components/ui/native-select';
	import * as Card from '$lib/components/ui/card';
	import type { Channel } from './communities';
	import { communityRequest } from './communities';

	let { communityId, channels, role }: { communityId: number; channels: Channel[]; role: string } =
		$props();
	let modes = $state<Record<number, string>>({});
	let saving = $state<Record<number, boolean>>({});
	let error = $state('');
	const visibleChannels = $derived(
		channels.filter(
			(channel) => role === 'owner' || role === 'moderator' || (!channel.private && !channel.locked)
		)
	);

	onMount(() => {
		let current = true;
		void Promise.all(
			visibleChannels.map(async (channel) => {
				try {
					const result = await communityRequest<{ alerts: string }>(
						`/communities/${communityId}/channels/${channel.id}/presence`
					);
					if (current) modes[channel.id] = result.alerts;
				} catch (cause) {
					if (current)
						error = cause instanceof Error ? cause.message : 'Could not load preferences';
				}
			})
		);
		return () => {
			current = false;
		};
	});

	async function setMode(channel: Channel, value: string) {
		saving[channel.id] = true;
		try {
			await communityRequest(`/communities/${communityId}/channels/${channel.id}/alerts`, 'PUT', {
				alerts: value
			});
			modes[channel.id] = value;
			error = '';
		} catch (cause) {
			error = cause instanceof Error ? cause.message : 'Could not save preferences';
		} finally {
			saving[channel.id] = false;
		}
	}
</script>

<Card.Root id="community-notifications" class="settings-section">
	<div class="settings-section-head">Notification settings</div>
	<p class="settings-help">Choose what appears in your inbox for each channel.</p>
	{#if error}<p role="alert">{error}</p>{/if}
	{#each visibleChannels as channel (channel.id)}
		<label class="channel-alert-setting">
			<span>#{channel.name}</span>
			<NativeSelect
				aria-label={`Inbox notifications for ${channel.name}`}
				disabled={saving[channel.id] || modes[channel.id] === undefined}
				value={modes[channel.id] ?? 'all'}
				onchange={(event) => void setMode(channel, event.currentTarget.value)}
			>
				<option value="all">All messages</option>
				<option value="mentions">Mentions only</option>
				<option value="muted">Muted</option>
			</NativeSelect>
		</label>
	{:else}
		<p class="settings-help">No channels are available for notification preferences.</p>
	{/each}
</Card.Root>

<style>
	.settings-help {
		margin: 0 0 10px;
		color: var(--muted);
		font-size: 12px;
		line-height: 1.45;
	}
	.channel-alert-setting {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 14px;
		padding: 8px 0;
		border-top: 1px solid var(--line);
		font-size: 12px;
	}
	.channel-alert-setting > span {
		min-width: 0;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.channel-alert-setting :global(select) {
		width: 150px;
		flex: none;
	}
</style>
