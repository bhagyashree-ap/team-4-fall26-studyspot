<script lang="ts">
	import { renderMessage } from './markdown';
	const legacyEmoji: Record<string, string> = {
		':sticker:study:': '📚',
		':sticker:break:': '☕',
		':sticker:done:': '🎉'
	};
	let { content }: { content: string } = $props();
</script>

<div class="body">
	<!-- eslint-disable-next-line svelte/no-at-html-tags -- parser disables HTML and escapes spoiler text -->
	{@html renderMessage(Object.hasOwn(legacyEmoji, content) ? legacyEmoji[content] : content)}
</div>

<style>
	.body > :global(div + div) {
		margin-top: 8px;
	}
	.body :global(ul) {
		list-style: disc;
		padding-left: 1.3em;
		margin-block: 8px;
	}
	.body :global(ol) {
		list-style: decimal;
		padding-left: 1.3em;
		margin-block: 8px;
	}
	.body :global(blockquote) {
		border-left: 2px solid currentColor;
		padding-left: 12px;
		margin-block: 8px;
		opacity: 0.85;
	}
	.body :global(h1),
	.body :global(h2),
	.body :global(h3) {
		font-size: 1.05em;
		font-weight: 600;
		margin-block: 8px;
	}
	.body :global(strong) {
		font-weight: 650;
	}
	.body :global(em) {
		font-style: italic;
	}
	.body :global(code) {
		font-size: 0.88em;
	}

	.body {
		overflow-wrap: anywhere;
	}
	.body :global(pre) {
		overflow: auto;
		background: #222;
		color: white;
		padding: 0.6rem;
	}
	.body :global(summary) {
		cursor: pointer;
	}
	.body :global(a) {
		text-decoration: underline;
	}
</style>
