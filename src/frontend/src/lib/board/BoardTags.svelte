<script lang="ts">
	import { boardUrl, tagLabels, type BoardFilters, type TagView } from '$lib/board';
	let { tags, filters = {} }: { tags: TagView[]; filters?: Partial<BoardFilters> } = $props();
</script>

{#if tags.length}
	<ul class="board-tags" aria-label="Post tags">
		{#each tags as tag (`${tag.kind}:${tag.value}`)}
			<li>
				<a href={boardUrl({ ...filters, [tag.kind]: tag.value })}>
					<span>{tagLabels[tag.kind]}:</span>
					{tag.label}
					{#if !tag.available}<span>(no longer listed)</span>{/if}
				</a>
			</li>
		{/each}
	</ul>
{/if}
