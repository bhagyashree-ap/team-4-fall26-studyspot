<script lang="ts">
	import { onDestroy } from 'svelte';
	import { searchSpots } from '$lib/api';
	import { boardError, fetchBoardTags, tagLabels, type TagKind, type TagView } from '$lib/board';

	let { tags = $bindable([]), disabled = false }: { tags?: TagView[]; disabled?: boolean } =
		$props();
	const id = $props.id();
	let kind = $state<TagKind>('subject');
	let query = $state('');
	let suggestions = $state<TagView[]>([]);
	let searching = $state(false);
	let error = $state('');
	let searched = $state(false);
	let request = 0;
	let alive = true;
	onDestroy(() => {
		alive = false;
		request++;
	});

	$effect(() => {
		const selectedKind = kind;
		const text = query.trim();
		const current = ++request;
		suggestions = [];
		error = '';
		searched = false;
		searching = false;
		if (!text) return;
		searching = true;
		const timer = setTimeout(async () => {
			try {
				const found =
					selectedKind === 'spot'
						? (await searchSpots(text, { limit: 8 })).items.map((spot) => ({
								kind: 'spot' as const,
								value: spot.id,
								label: spot.name,
								available: true
							}))
						: (await fetchBoardTags(selectedKind, text)).items;
				if (alive && current === request) {
					suggestions = found;
					searched = true;
				}
			} catch (cause) {
				if (alive && current === request) error = boardError(cause);
			} finally {
				if (alive && current === request) searching = false;
			}
		}, 250);
		return () => clearTimeout(timer);
	});

	function add(tag: TagView) {
		if (disabled || tags.length >= 10) return;
		if (tags.some((existing) => existing.kind === tag.kind && existing.value === tag.value)) {
			error = 'This tag is already added.';
			return;
		}
		tags = [...tags, tag];
		query = '';
	}
	function addText() {
		if (kind === 'spot' || !query.trim()) return;
		const label = query.normalize('NFKC').trim().replace(/\s+/g, ' ');
		add({ kind, value: label, label, available: true });
	}
</script>

<fieldset class="board-tag-picker" {disabled}>
	<legend>Tags <span class="board-muted">(up to 10)</span></legend>
	<p class="board-help" id={`${id}-help`}>
		Add any subject or university. Choose study spots from search results. You can add more than one
		tag of each kind.
	</p>
	{#if tags.length}
		<ul class="board-tags" aria-label="Selected tags">
			{#each tags as tag, index (`${tag.kind}:${tag.value}`)}
				<li class="board-selected-tag">
					<span
						>{tagLabels[tag.kind]}: {tag.label}{!tag.available ? ' (no longer listed)' : ''}</span
					>
					<button
						type="button"
						aria-label={`Remove ${tagLabels[tag.kind].toLowerCase()} tag ${tag.label}`}
						onclick={() => (tags = tags.filter((_, position) => position !== index))}>Remove</button
					>
				</li>
			{/each}
		</ul>
	{/if}
	<div class="board-tag-entry">
		<div class="board-field">
			<label for={`${id}-kind`}>Tag type</label>
			<select id={`${id}-kind`} bind:value={kind}>
				<option value="subject">Subject</option>
				<option value="university">University</option>
				<option value="spot">Study spot</option>
			</select>
		</div>
		<div class="board-field board-grow">
			<label for={`${id}-query`}
				>{kind === 'spot' ? 'Study spot search' : `${tagLabels[kind]} tag`}</label
			>
			<input
				id={`${id}-query`}
				bind:value={query}
				maxlength={kind === 'subject' ? 80 : kind === 'university' ? 120 : 255}
				aria-describedby={`${id}-help`}
				autocomplete="off"
				onkeydown={(event) => {
					if (event.key === 'Enter') {
						event.preventDefault();
						addText();
					}
				}}
			/>
		</div>
		{#if kind !== 'spot'}
			<button type="button" disabled={!query.trim() || tags.length >= 10} onclick={addText}
				>Add tag</button
			>
		{/if}
	</div>
	{#if searching}<p class="board-help" role="status">
			Finding {kind === 'spot' ? 'study spots' : 'tags'}…
		</p>{/if}
	{#if error}<p class="board-error" role="alert">{error}</p>{/if}
	{#if suggestions.length}
		<ul
			class="board-suggestions"
			aria-label={kind === 'spot' ? 'Study spot results' : 'Tag suggestions'}
		>
			{#each suggestions as tag (`${tag.kind}:${tag.value}`)}
				<li>
					<button type="button" disabled={tags.length >= 10} onclick={() => add(tag)}
						>{kind === 'spot' ? 'Choose' : 'Add'} {tag.label}</button
					>
				</li>
			{/each}
		</ul>
	{:else if searched && kind === 'spot'}
		<p class="board-help" role="status">No study spots found. Try another name.</p>
	{/if}
</fieldset>
