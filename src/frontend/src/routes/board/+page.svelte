<script lang="ts">
	import { onMount } from 'svelte';
	import SiteHeader from '$lib/SiteHeader.svelte';
	import BoardPage from '$lib/board/BoardPage.svelte';
	import { session } from '$lib/session.svelte';
	import '$lib/board/board.css';

	let ready = $state(false);
	const identity = $derived(
		JSON.stringify([session.status, session.account?.email, session.account?.account_type])
	);
	onMount(() => {
		let alive = true;
		void session.start().then(() => {
			if (alive) ready = true;
		});
		return () => {
			alive = false;
		};
	});
</script>

<svelte:head>
	<title>Public board · StudySpot</title>
	<meta
		name="description"
		content="Ask questions, share information, and discuss study spots on the public board."
	/>
</svelte:head>

<div class="board">
	<SiteHeader />
	<main id="board-main">
		{#if ready && session.status !== 'loading'}
			{#key identity}<BoardPage />{/key}
		{:else}
			<h1>Public board</h1>
			<p role="status">Loading your session…</p>
		{/if}
	</main>
</div>
