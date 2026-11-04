<script lang="ts">
	import { Input } from '$lib/components/ui/input';
	import { Textarea } from '$lib/components/ui/textarea';
	import { Button } from '$lib/components/ui/button';
	import { communityRequest } from './communities';
	let { url, onsent }: { url: string; onsent: () => void } = $props();
	let question = $state(''),
		choices = $state(''),
		error = $state(''),
		busy = $state(false),
		opened = $state(false);
	async function create() {
		if (busy) return;
		busy = true;
		try {
			await communityRequest(url, 'POST', {
				content: question,
				options: choices
					.split('\n')
					.map((s) => s.trim())
					.filter(Boolean)
			});
			question = choices = error = '';
			opened = false;
			onsent();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Poll failed';
		} finally {
			busy = false;
		}
	}
</script>

<details bind:open={opened}>
	<summary>Create poll</summary><label
		>Question<Input bind:value={question} maxlength={2000} /></label
	><label>Choices (one per line)<Textarea bind:value={choices}></Textarea></label><Button
		variant="ghost"
		size="sm"
		type="button"
		disabled={busy || !question.trim()}
		onclick={create}>Post poll</Button
	>{#if error}<span role="alert">{error}</span>{/if}
</details>
