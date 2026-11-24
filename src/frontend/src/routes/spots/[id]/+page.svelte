<script lang="ts">
	import SpotDetail from '$lib/SpotDetail.svelte';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
</script>

<SpotDetail spot={data.spot} nearby={data.nearby} />
