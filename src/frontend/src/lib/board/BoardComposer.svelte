<script lang="ts">
	import { onDestroy, untrack } from 'svelte';
	import {
		boardError,
		kindLabels,
		type BoardAccess,
		type BoardPost,
		type PostDraft,
		type PostKind,
		type TagView
	} from '$lib/board';
	import BoardTagPicker from './BoardTagPicker.svelte';

	let {
		access,
		initial,
		onsubmit,
		oncancel
	}: {
		access: BoardAccess;
		initial?: BoardPost;
		onsubmit: (draft: PostDraft) => Promise<void>;
		oncancel: () => void;
	} = $props();
	const id = $props.id();
	let kind = $state<PostKind>(untrack(() => initial?.kind ?? access.create_kinds[0] ?? 'question'));
	let title = $state(untrack(() => initial?.title ?? ''));
	let body = $state(untrack(() => initial?.body ?? ''));
	let tags = $state<TagView[]>(untrack(() => initial?.tags.map((tag) => ({ ...tag })) ?? []));
	let saving = $state(false);
	let error = $state('');
	let alive = true;
	onDestroy(() => (alive = false));

	async function submit(event: SubmitEvent) {
		event.preventDefault();
		if (saving) return;
		if (!title.trim() || !body.trim()) {
			error = 'Enter a title and a message before posting.';
			return;
		}
		saving = true;
		error = '';
		try {
			await onsubmit({ kind, title, body, tags: tags.map(({ kind, value }) => ({ kind, value })) });
		} catch (cause) {
			if (alive) error = `${boardError(cause)} Your draft is still here. Try again when ready.`;
		} finally {
			if (alive) saving = false;
		}
	}
</script>

<form class="board-composer" aria-label={initial ? 'Edit post' : 'New post'} onsubmit={submit}>
	<h1>{initial ? 'Edit post' : 'New post'}</h1>
	<fieldset disabled={saving}>
		<div class="board-field">
			<label for={`${id}-kind`}>Post type</label>
			<select id={`${id}-kind`} bind:value={kind}>
				{#each access.create_kinds as option (option)}
					<option value={option}>{kindLabels[option]}</option>
				{/each}
				{#if initial && !access.create_kinds.includes(initial.kind)}
					<option value={initial.kind}>{kindLabels[initial.kind]}</option>
				{/if}
			</select>
		</div>
		<div class="board-field">
			<label for={`${id}-title`}>Title</label>
			<input id={`${id}-title`} bind:value={title} maxlength={access.limits.title} required />
		</div>
		<div class="board-field">
			<label for={`${id}-body`}>Message</label>
			<textarea id={`${id}-body`} bind:value={body} maxlength={access.limits.body} rows="9" required
			></textarea>
			<p class="board-help">Plain text only. Line breaks are preserved.</p>
		</div>
		<BoardTagPicker bind:tags disabled={saving} />
	</fieldset>
	{#if error}<p class="board-error" role="alert">{error}</p>{/if}
	{#if saving}<p role="status">{initial ? 'Saving changes…' : 'Publishing post…'}</p>{/if}
	<div class="board-actions">
		<button class="board-primary" type="submit" disabled={saving}>
			{saving ? 'Saving…' : initial ? 'Save changes' : 'Publish post'}
		</button>
		<button type="button" disabled={saving} onclick={oncancel}>Cancel</button>
	</div>
</form>
