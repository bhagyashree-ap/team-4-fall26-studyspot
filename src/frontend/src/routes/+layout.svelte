<script lang="ts">
	import './layout.css';
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { CALLBACK_PATH, session } from '$lib/session.svelte';

	let { children } = $props();

	// Every page is prerendered, so who is logged in is only knowable here, once
	// the browser is running the app.
	onMount(() => {
		void session.start({ callback: page.url.pathname === CALLBACK_PATH });
	});
</script>

{@render children()}
