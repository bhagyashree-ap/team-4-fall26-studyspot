<script lang="ts">
	import './layout.css';
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { CALLBACK_PATH, session } from '$lib/session.svelte';
	import { communityRequest } from '$lib/communities';

	let { children } = $props();

	// Every page is prerendered, so who is logged in is only knowable here, once
	// the browser is running the app.
	onMount(() => {
		let timer: ReturnType<typeof setInterval> | undefined;
		const heartbeat = () => {
			if (document.visibilityState === 'visible')
				void communityRequest('/chat/presence', 'POST').catch(() => {});
		};
		void session.start({ callback: page.url.pathname === CALLBACK_PATH }).then(async () => {
			try {
				await communityRequest('/communities/access');
				heartbeat();
				timer = setInterval(heartbeat, 30_000);
			} catch {
				// A failed presence check must never block the page.
			}
		});
		const visibilityChanged = () => heartbeat();
		document.addEventListener('visibilitychange', visibilityChanged);
		return () => {
			if (timer) clearInterval(timer);
			document.removeEventListener('visibilitychange', visibilityChanged);
		};
	});
</script>

{@render children()}
