<script lang="ts">
	import ArrowUp from '@lucide/svelte/icons/arrow-up';
	import Search from '@lucide/svelte/icons/search';
	import Plus from '@lucide/svelte/icons/plus';
	import ArrowUpRight from '@lucide/svelte/icons/arrow-up-right';
	import MessageCircle from '@lucide/svelte/icons/message-circle';
	import Users from '@lucide/svelte/icons/users';
	import X from '@lucide/svelte/icons/x';
	import Moon from '@lucide/svelte/icons/moon';
	import Sun from '@lucide/svelte/icons/sun';
	import { tick } from 'svelte';
	import type { Community } from './communities';

	let {
		communities,
		query = $bindable(''),
		mine = $bindable(false),
		loading,
		hasMore,
		joining,
		error,
		onopen,
		onjoin,
		oncreate,
		onmessages,
		theme = 'light',
		ontheme = () => {},
		onmore,
		onbacktotop
	}: {
		communities: Community[];
		query?: string;
		mine?: boolean;
		loading: boolean;
		hasMore: boolean;
		joining: number | null;
		error: string;
		onopen: (community: Community) => void;
		onjoin: (community: Community) => Promise<void>;
		oncreate: () => void;
		onmessages: (event: MouseEvent) => void;
		theme?: 'light' | 'dark';
		ontheme?: () => void;
		onmore: () => void;
		onbacktotop: (event: MouseEvent) => void;
	} = $props();
	let inspecting = $state<Community | null>(null);
	let previewDialog: HTMLDialogElement;
	let previewMotion = $state(false);
	async function showPreview(community: Community, event: MouseEvent) {
		inspecting = community;
		previewMotion = event.detail > 0;
		await tick();
		previewDialog.showModal();
	}
	const tones = ['#e9eee3', '#ece6f2', '#f4e8da', '#e0ecec', '#eee4e6'];
	function tone(name: string) {
		let hash = 0;
		for (const letter of name) hash = (hash * 31 + letter.charCodeAt(0)) | 0;
		return tones[Math.abs(hash) % tones.length];
	}
	function initials(name: string) {
		return name
			.trim()
			.split(/\s+/)
			.slice(0, 2)
			.map((word) => word[0])
			.join('')
			.toUpperCase();
	}
</script>

<section class="discovery" aria-labelledby="discovery-title">
	<div class="discovery-top">
		<div>
			<p class="eyebrow">A little company. A little progress.</p>
			<h1 id="discovery-title" tabindex="-1">Find your study people.</h1>
		</div>
		<div class="top-actions">
			<button
				class="quiet theme-toggle"
				aria-label={theme === 'light' ? 'Switch to dark mode' : 'Switch to light mode'}
				title={theme === 'light' ? 'Switch to dark mode' : 'Switch to light mode'}
				onclick={ontheme}
				>{#if theme === 'light'}<Moon size={16} />{:else}<Sun size={16} />{/if}<span
					>{theme === 'light' ? 'Dark mode' : 'Light mode'}</span
				></button
			>
			<button class="quiet" onclick={onmessages}><MessageCircle size={17} /> Messages</button>
			<button class="primary" onclick={oncreate}><Plus size={17} /> Create community</button>
		</div>
	</div>
	<div class="search-wrap">
		<Search size={20} aria-hidden="true" />
		<input
			aria-label="Search communities"
			placeholder="Search communities, schools, or courses"
			maxlength={100}
			bind:value={query}
		/>
		{#if query}<button class="clear" aria-label="Clear search" onclick={() => (query = '')}
				><X size={16} /></button
			>{/if}
	</div>
	<div class="browse-bar">
		<div class="tabs" role="group" aria-label="Community collection">
			<button aria-pressed={!mine} onclick={() => (mine = false)}>Discover</button>
			<button aria-pressed={mine} onclick={() => (mine = true)}>My communities</button>
		</div>
		<p class="result-note" role="status">
			{loading
				? 'Finding your people…'
				: query.trim()
					? `Results for “${query.trim()}”`
					: mine
						? 'Your spaces to make progress'
						: 'Public spaces. Shared goals.'}
		</p>
	</div>
	{#if communities.length}
		<div class="masonry" aria-label="Communities" aria-busy={loading}>
			{#each communities as community (community.id)}
				<article class="community-card" class:arriving={!query.trim() && !mine}>
					<div class="card-link">
						<div class="card-top">
							<span class="monogram" style:background={tone(community.name)}
								>{initials(community.name)}</span
							>
							{#if community.role !== 'visitor'}
								<span class="membership"
									>{community.role === 'owner' ? 'Your community' : 'Joined'}</span
								>
							{/if}
						</div>
						{#if community.course}<span class="course">{community.course}</span>{/if}
						<h2>{community.name}</h2>
						{#if community.description}<p class="description">{community.description}</p>{/if}
						{#if community.school}<p class="school">{community.school}</p>{/if}
						<div class="card-footer">
							<span
								><Users size={15} />{community.member_count}
								{community.member_count === 1 ? 'member' : 'members'}</span
							>
							<button
								class="card-action"
								aria-label={(community.role === 'visitor' ? 'Take a look at ' : 'Open chat in ') +
									community.name}
								onclick={(event) =>
									community.role === 'visitor'
										? void showPreview(community, event)
										: onopen(community)}
							>
								{community.role === 'visitor' ? 'Take a look' : 'Open chat'}<ArrowUpRight
									size={15}
								/>
							</button>
						</div>
					</div>
				</article>
			{/each}
		</div>
	{:else if loading}
		<div class="empty" role="status"><p>Finding your people…</p></div>
	{:else if !error}
		<div class="empty">
			<h2>
				{query.trim()
					? 'No communities found'
					: mine
						? 'Your next study group starts here.'
						: 'Be the first to bring people together.'}
			</h2>
			<p>
				{query.trim()
					? 'Try another school, course, or community name.'
					: mine
						? 'Explore a community or create a space of your own.'
						: 'Create a community for your course, project, or shared interest.'}
			</p>
			<button
				class="primary"
				onclick={query.trim() ? () => (query = '') : mine ? () => (mine = false) : oncreate}
				>{query.trim()
					? 'Clear search'
					: mine
						? 'Discover communities'
						: 'Create community'}</button
			>
		</div>
	{/if}
	{#if hasMore}<div class="pagination">
			<button class="quiet" disabled={loading} onclick={onmore}
				>{loading ? 'Loading…' : 'Load more communities'}</button
			>
		</div>{/if}
	{#if communities.length}<div class="back-to-top">
			<button class="quiet" onclick={onbacktotop}><ArrowUp size={16} /> Back to top</button>
		</div>{/if}
</section>

<dialog
	class="community-preview"
	aria-labelledby="preview-name"
	bind:this={previewDialog}
	data-motion={previewMotion}
	oncancel={() => (previewMotion = false)}
>
	{#if inspecting}
		<button
			class="close quiet"
			aria-label="Close community preview"
			onclick={(event) => {
				previewMotion = event.detail > 0;
				previewDialog.close();
			}}><X size={18} /></button
		>
		<span class="monogram large" style:background={tone(inspecting.name)}
			>{initials(inspecting.name)}</span
		>
		<p class="eyebrow">Public study community</p>
		<h2 id="preview-name">{inspecting.name}</h2>
		{#if inspecting.school || inspecting.course}<p class="school">
				{[inspecting.school, inspecting.course].filter(Boolean).join(' · ')}
			</p>{/if}
		<p class="preview-description">
			{inspecting.description ||
				'A shared space to study, ask questions, and make progress together.'}
		</p>
		<p class="member-count">
			<Users size={16} />
			{inspecting.member_count}
			{inspecting.member_count === 1 ? 'member' : 'members'}
		</p>
		{#if error}<p role="alert">{error}</p>{/if}
		<button
			class="primary join"
			disabled={joining !== null}
			onclick={() => inspecting && void onjoin(inspecting)}
			>{joining !== null ? 'Joining…' : 'Join community'}<ArrowUpRight size={17} /></button
		>
	{/if}
</dialog>

<style>
	.back-to-top {
		display: flex;
		justify-content: center;
		padding-top: 28px;
	}
	#discovery-title {
		outline: none;
	}
	.discovery {
		max-width: 1440px;
		width: 100%;
		margin-inline: auto;
		padding: 44px clamp(20px, 4vw, 64px) 72px;
	}
	.discovery-top,
	.top-actions,
	.search-wrap,
	.browse-bar,
	.tabs,
	.card-top,
	.card-footer,
	.card-footer > span,
	.member-count {
		display: flex;
		align-items: center;
	}
	.discovery-top {
		justify-content: space-between;
		gap: 24px;
	}
	.eyebrow {
		margin: 0 0 8px;
		font-size: 12px;
		color: var(--muted);
	}
	h1 {
		margin: 0;
		font-size: clamp(26px, 3vw, 38px);
		line-height: 1.2;
		letter-spacing: -0.045em;
		font-weight: 600;
	}
	.top-actions {
		gap: 10px;
	}
	button {
		font: inherit;
		cursor: pointer;
	}
	.primary,
	.quiet {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		gap: 8px;
		border-radius: 10px;
		padding: 11px 15px;
		font-size: 13px;
		font-weight: 550;
		min-height: 44px;
	}
	.primary {
		background: var(--ink);
		color: var(--panel);
		border: 1px solid var(--ink);
	}
	.quiet {
		background: var(--panel);
		color: var(--ink);
		border: 1px solid var(--line);
	}
	button:disabled {
		opacity: 0.6;
		cursor: wait;
	}
	button:focus-visible,
	input:focus-visible {
		outline: 2px solid var(--ink);
		outline-offset: 4px;
	}
	.search-wrap {
		max-width: 640px;
		margin: 36px auto 32px;
		background: var(--panel);
		border: 1px solid var(--line);
		border-radius: 16px;
		padding: 0 18px;
		gap: 12px;
		color: var(--muted);
		box-shadow: 0 2px 5px #29251f03;
	}
	.search-wrap:focus-within {
		border-color: var(--muted);
	}
	input {
		width: 100%;
		height: 56px;
		border: 0;
		background: transparent;
		font: inherit;
		font-size: 16px;
		min-width: 0;
		outline: none;
	}
	input:focus-visible {
		outline-offset: -4px;
		border-radius: 6px;
	}
	.clear {
		display: grid;
		place-items: center;
		width: 36px;
		height: 40px;
		border: 0;
		background: transparent;
		color: var(--muted);
		flex: none;
	}
	.browse-bar {
		justify-content: space-between;
		gap: 16px;
		border-bottom: 1px solid var(--line);
		margin-bottom: 28px;
	}
	.tabs {
		gap: 24px;
	}
	.tabs button {
		background: transparent;
		color: var(--muted);
		border: 0;
		border-bottom: 2px solid transparent;
		padding: 14px 0;
		min-height: 48px;
		font-size: 14px;
	}
	.tabs button[aria-pressed='true'] {
		color: var(--ink);
		border-bottom-color: var(--ink);
		font-weight: 600;
	}
	.result-note {
		color: var(--muted);
		font-size: 12px;
		margin: 0;
	}
	.masonry {
		columns: 4;
		column-gap: 20px;
	}
	.community-card {
		break-inside: avoid;
		margin: 0 0 20px;
		border: 1px solid var(--line);
		border-radius: 16px;
		background: var(--panel);
		overflow: hidden;
	}
	.card-link {
		display: block;
		width: 100%;
		padding: 22px;
		border: 0;
		background: transparent;
		text-align: left;
		color: var(--ink);
	}
	.card-top {
		gap: 10px;
		margin-bottom: 28px;
	}
	.monogram {
		display: inline-grid;
		place-items: center;
		width: 40px;
		height: 40px;
		flex: none;
		border-radius: 12px;
		color: #41443b;
		font-size: 13px;
		font-weight: 600;
	}
	.membership {
		color: var(--muted);
		font-size: 11px;
	}
	.course {
		display: block;
		margin-bottom: 8px;
		color: var(--muted);
		font-size: 11px;
		font-weight: 600;
		letter-spacing: 0.04em;
		overflow-wrap: anywhere;
	}
	h2 {
		margin: 0;
		font-size: 19px;
		font-weight: 600;
		line-height: 1.3;
		letter-spacing: -0.025em;
		overflow-wrap: anywhere;
	}
	.description {
		color: var(--muted);
		font-size: 14px;
		line-height: 1.65;
		margin: 12px 0 0;
		display: -webkit-box;
		line-clamp: 6;
		-webkit-line-clamp: 6;
		-webkit-box-orient: vertical;
		overflow: hidden;
		overflow-wrap: anywhere;
		white-space: pre-line;
	}
	.school {
		color: var(--muted);
		font-size: 12px;
		line-height: 1.5;
		margin: 18px 0 0;
		overflow-wrap: anywhere;
	}
	.card-footer {
		justify-content: space-between;
		flex-wrap: wrap;
		gap: 12px;
		border-top: 1px solid var(--line);
		padding-top: 16px;
		margin-top: 24px;
		color: var(--muted);
		font-size: 11px;
	}
	.card-footer > span {
		gap: 6px;
	}
	.card-action {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		gap: 8px;
		min-height: 40px;
		padding: 9px 12px;
		border: 1px solid var(--ink);
		border-radius: 9px;
		background: var(--ink);
		color: var(--panel);
		font-size: 12px;
		font-weight: 550;
	}
	.empty {
		text-align: center;
		padding: 72px 16px;
	}
	.empty p {
		color: var(--muted);
		margin: 12px auto 24px;
		max-width: 380px;
	}
	.pagination {
		text-align: center;
		margin-top: 24px;
	}
	.community-preview {
		margin: auto;
		width: min(480px, calc(100% - 32px));
		max-height: calc(100dvh - 32px);
		overflow-y: auto;
		padding: 32px;
		border: 1px solid var(--line);
		border-radius: 20px;
		background: var(--panel);
		color: var(--ink);
		box-shadow: 0 24px 80px #0002;
	}
	.community-preview::backdrop {
		background: #191b2080;
	}
	.close {
		position: absolute;
		top: 12px;
		right: 12px;
		padding: 10px;
		border: 0;
	}
	.large {
		width: 56px;
		height: 56px;
		font-size: 18px;
		margin-bottom: 24px;
	}
	.community-preview h2 {
		font-size: 28px;
	}
	.preview-description {
		margin: 24px 0;
		line-height: 1.7;
		white-space: pre-wrap;
		overflow-wrap: anywhere;
	}
	.member-count {
		gap: 8px;
		color: var(--muted);
		font-size: 13px;
	}
	.join {
		margin-top: 16px;
		width: 100%;
	}
	@media (hover: hover) and (pointer: fine) {
		.community-card:hover {
			border-color: var(--muted);
		}
		.quiet:hover {
			background: var(--well);
		}
		.primary:hover {
			opacity: 0.88;
		}
	}
	.community-preview[data-motion] {
		animation: none;
	}
	@media (prefers-reduced-motion: no-preference) {
		.community-card {
			transition:
				background-color 220ms ease,
				border-color 220ms ease,
				color 220ms ease,
				transform 180ms var(--ease-out),
				opacity 180ms var(--ease-out);
		}
		@starting-style {
			.community-card.arriving {
				opacity: 0;
				transform: translateY(10px);
			}
		}
		.primary,
		.quiet,
		.card-action {
			transition:
				background-color 220ms ease,
				border-color 220ms ease,
				color 220ms ease,
				transform 120ms var(--ease-out),
				opacity 120ms ease;
		}
		.search-wrap,
		.tabs button,
		.community-preview {
			transition:
				background-color 220ms ease,
				border-color 220ms ease,
				color 220ms ease;
		}
		.primary:active:not(:focus-visible),
		.quiet:active:not(:focus-visible),
		.card-action:active:not(:focus-visible) {
			transform: scale(0.97);
		}
		.card-action :global(svg) {
			transition: transform 160ms var(--ease-out);
		}
		@media (hover: hover) and (pointer: fine) {
			.community-card:hover {
				transform: translateY(-3px);
			}
			.card-action:hover :global(svg) {
				transform: translate(2px, -2px);
			}
		}
		.community-preview[data-motion='true'] {
			opacity: 0;
			transform: translateY(8px) scale(0.97);
			transition:
				opacity 160ms var(--ease-out),
				transform 160ms var(--ease-out),
				display 160ms allow-discrete,
				overlay 160ms allow-discrete;
		}
		.community-preview[data-motion='true'][open] {
			opacity: 1;
			transform: translateY(0) scale(1);
			transition-duration: 220ms;
		}
		.community-preview[data-motion='true']::backdrop {
			opacity: 0;
			transition:
				opacity 160ms var(--ease-out),
				display 160ms allow-discrete,
				overlay 160ms allow-discrete;
		}
		.community-preview[data-motion='true'][open]::backdrop {
			opacity: 1;
			transition-duration: 220ms;
		}
		@starting-style {
			.community-preview[data-motion='true'][open] {
				opacity: 0;
				transform: translateY(8px) scale(0.97);
			}
			.community-preview[data-motion='true'][open]::backdrop {
				opacity: 0;
			}
		}
	}
	@media (max-width: 1200px) {
		.masonry {
			columns: 3;
		}
	}
	@media (max-width: 940px) {
		.masonry {
			columns: 2;
		}
		.discovery-top {
			align-items: flex-start;
			flex-direction: column;
		}
	}
	@media (max-width: 560px) {
		.discovery {
			padding-top: 28px;
		}
		.masonry {
			columns: 1;
		}
		.result-note {
			display: none;
		}
		.search-wrap {
			margin-top: 28px;
		}
		.top-actions {
			flex-wrap: wrap;
		}
		.card-top {
			margin-bottom: 20px;
		}
	}
</style>
