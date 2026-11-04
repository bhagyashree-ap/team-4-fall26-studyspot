<script lang="ts">
	import Attachment from './Attachment.svelte';
	import Ballot from './Ballot.svelte';
	import { communityRequest, type DirectMessage } from './communities';
	import MessageBody from './MessageBody.svelte';
	import { onMount } from 'svelte';
	let { url, loaded }: { url: string; loaded: { id: number }[] } = $props();
	let linked = $state<DirectMessage | null>(null);
	let error = $state('');
	let visibleTarget = $derived(
		linked && loaded.some((item) => item.id === linked?.id) ? linked.id : null
	);
	$effect(() => {
		if (visibleTarget !== null)
			document.getElementById(`message-${visibleTarget}`)?.scrollIntoView({ block: 'nearest' });
	});
	onMount(() => {
		let current = 0;
		async function open() {
			const version = ++current;
			linked = null;
			error = '';
			const match = /^#message-(\d+)$/.exec(location.hash);
			if (!match) return;
			try {
				const item = await communityRequest<DirectMessage>(url + '/' + match[1]);
				if (version === current) linked = item;
			} catch {
				if (version === current) error = 'This linked message is unavailable.';
			}
		}
		void open();
		window.addEventListener('hashchange', open);
		return () => {
			current++;
			window.removeEventListener('hashchange', open);
		};
	});
</script>

{#if linked && !loaded.some((m) => m.id === linked?.id)}<aside aria-label="Linked message">
		<strong>Linked message · {linked.author_name}</strong><MessageBody
			content={linked.deleted_at ? 'Message deleted' : linked.content}
		/>
		{#if !linked.deleted_at && linked.file_name}<Attachment
				url={url + '/' + linked.id}
				name={linked.file_name}
			/>{/if}
		{#if !linked.deleted_at && linked.poll}<Ballot
				poll={linked.poll}
				url={url + '/' + linked.id + '/vote'}
				onvote={(poll) => {
					if (linked) linked = { ...linked, poll };
				}}
			/>{/if}
	</aside>{:else if error}<p>{error}</p>{/if}
