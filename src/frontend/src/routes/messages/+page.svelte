<script lang="ts">
	import { onMount, tick } from 'svelte';
	import { SvelteURLSearchParams } from 'svelte/reactivity';
	import { goto, replaceState } from '$app/navigation';
	import { resolve } from '$app/paths';
	import SiteHeader from '$lib/SiteHeader.svelte';
	import MessagesInbox from '$lib/MessagesInbox.svelte';
	import DirectMessages from '$lib/DirectMessages.svelte';
	import { communityRequest, type DirectConversation } from '$lib/communities';
	import { session } from '$lib/session.svelte';
	import '$lib/chat-theme.css';
	import Search from '@lucide/svelte/icons/search';
	import X from '@lucide/svelte/icons/x';
	import ArrowLeft from '@lucide/svelte/icons/arrow-left';

	type Person = {
		name: string;
		community: string;
		community_id: number;
		target: { user_id: string } | { guest_member_id: number };
	};
	let conversations = $state<DirectConversation[]>([]);
	let selected = $state<DirectConversation | null>(null);
	let composing = $state(false);
	let composeKind = $state<'direct' | 'group'>('direct');
	let groupName = $state('');
	let groupPeople = $state<Person[]>([]);
	let creatingGroup = $state(false);
	let recipientInput: HTMLInputElement;
	let query = $state('');
	let people = $state<Person[]>([]);
	let peopleStatus = $state('');
	let loading = $state(true);
	let ready = $state(false);
	let error = $state('');
	let theme = $state<'light' | 'dark'>('light');
	let headerHeight = $state(76);
	let returnTo = $state('/communities');
	let returnLabel = $state('Communities');
	const problem = (cause: unknown) =>
		cause instanceof Error ? cause.message : 'Something went wrong.';
	function messagesPath(conversationId?: number) {
		const params = new SvelteURLSearchParams();
		if (conversationId) params.set('dm', String(conversationId));
		if (returnTo !== resolve('/communities')) {
			params.set('returnTo', returnTo);
			params.set('returnLabel', returnLabel);
		}
		return params.size ? resolve(`/messages?${params.toString()}`) : resolve('/messages');
	}
	function backToCommunity() {
		const communityRoot = resolve('/communities');
		// returnTo was validated to this resolved pathname during initialization.
		// eslint-disable-next-line svelte/no-navigation-without-resolve
		void goto(communityRoot + returnTo.slice(communityRoot.length));
	}

	async function refresh() {
		try {
			conversations = (await communityRequest<{ items: DirectConversation[] }>('/dms')).items;
			error = '';
		} catch (cause) {
			error = problem(cause);
		}
	}
	function toggleTheme() {
		theme = theme === 'dark' ? 'light' : 'dark';
		localStorage.setItem('studyspot.chat.theme', theme);
	}
	async function conversationAction(action: 'pin' | 'delete' | 'unread', item: DirectConversation) {
		try {
			if (action === 'pin') {
				await communityRequest(`/dms/${item.id}/preferences`, 'PUT', { pinned: !item.pinned });
			} else if (action === 'delete') {
				await communityRequest(`/dms/${item.id}/preferences`, 'DELETE');
			} else {
				const { items } = await communityRequest<{ items: { id: number }[] }>(
					`/dms/${item.id}/messages?limit=1`
				);
				const latest = items.at(-1)?.id;
				if (latest) {
					await communityRequest(`/dms/${item.id}/read`, 'PUT', { unread_from: latest });
					if (selected?.id === item.id) choose(null);
				}
			}
			await refresh();
		} catch (cause) {
			error = problem(cause);
		}
	}
	function choose(conversation: DirectConversation | null) {
		selected = conversation;
		composing = false;
		replaceState(messagesPath(conversation?.id), {});
	}
	async function newConversation(kind: 'direct' | 'group') {
		composeKind = kind;
		composing = true;
		selected = null;
		query = '';
		groupName = '';
		groupPeople = [];
		peopleStatus = '';
		replaceState(messagesPath(), {});
		await tick();
		recipientInput.focus();
	}
	async function createGroup() {
		if (creatingGroup || groupPeople.length < 2 || !groupName.trim()) return;
		creatingGroup = true;
		try {
			const conversation = await communityRequest<DirectConversation>('/dms', 'POST', {
				name: groupName.trim(),
				participants: groupPeople.map((person) => ({
					community_id: person.community_id,
					target: person.target
				}))
			});
			choose(conversation);
			await refresh();
		} catch (cause) {
			peopleStatus = problem(cause);
		} finally {
			creatingGroup = false;
		}
	}
	function addPerson(person: Person) {
		if (
			groupPeople.length < 19 &&
			!groupPeople.some((item) => JSON.stringify(item.target) === JSON.stringify(person.target))
		)
			groupPeople = [...groupPeople, person];
		query = '';
	}

	async function start(person: Person) {
		try {
			const conversation = await communityRequest<DirectConversation>(
				`/communities/${person.community_id}/dms`,
				'POST',
				person.target
			);
			choose(conversation);
			await refresh();
		} catch (cause) {
			peopleStatus = problem(cause);
		}
	}
	$effect(() => {
		const term = query.trim();
		people = [];
		peopleStatus = '';
		if (!composing || term.length < 2) return;
		let current = true;
		peopleStatus = 'Searching…';
		const timer = setTimeout(async () => {
			try {
				const result = await communityRequest<{ items: Person[] }>(
					`/chat/people?q=${encodeURIComponent(term)}`
				);
				if (current) {
					people = result.items;
					peopleStatus = result.items.length ? '' : 'No matching people in your communities.';
				}
			} catch (cause) {
				if (current) peopleStatus = problem(cause);
			}
		}, 180);
		return () => {
			current = false;
			clearTimeout(timer);
		};
	});
	onMount(() => {
		const saved = localStorage.getItem('studyspot.chat.theme');
		theme =
			saved === 'dark' || saved === 'light'
				? saved
				: matchMedia('(prefers-color-scheme: dark)').matches
					? 'dark'
					: 'light';
		let current = true;
		const initialUrl = new URL(location.href);
		const requestedReturn = initialUrl.searchParams.get('returnTo');
		if (requestedReturn) {
			const candidate = new URL(requestedReturn, location.origin);
			const communitiesPath = new URL(resolve('/communities'), location.origin).pathname;
			if (candidate.origin === location.origin && candidate.pathname === communitiesPath) {
				returnTo = candidate.pathname + candidate.search + candidate.hash;
				returnLabel = (initialUrl.searchParams.get('returnLabel') || 'Community').slice(0, 80);
			}
		}
		async function initialize() {
			try {
				const access = await communityRequest<{ guest_preview: boolean }>('/communities/access');
				if (!access.guest_preview) {
					await session.start();
					if (session.status === 'signed-out') {
						await session.logIn(location.pathname + location.search + location.hash);
						return;
					}
					if (session.status !== 'signed-in') throw new Error('Sign-in is unavailable.');
				}
				if (access.guest_preview && import.meta.env.DEV) {
					await communityRequest('/chat/demo', 'POST');
				}
				await refresh();
				const id = Number(new URL(location.href).searchParams.get('dm'));
				if (id) selected = await communityRequest<DirectConversation>(`/dms/${id}`);
				if (current) ready = true;
			} catch (cause) {
				if (current) error = problem(cause);
			} finally {
				if (current) loading = false;
			}
		}
		void initialize();
		const timer = setInterval(() => {
			if (ready && !document.hidden) void refresh();
		}, 8000);
		return () => {
			current = false;
			clearInterval(timer);
		};
	});
</script>

<svelte:head
	><title>Messages · StudySpot</title><meta name="robots" content="noindex" /></svelte:head
>
<div class="site-navigation" data-theme={theme} bind:clientHeight={headerHeight}>
	<SiteHeader />
</div>
<main
	class="chat-shell messages-screen"
	data-theme={theme}
	style:--site-header-height={headerHeight + 'px'}
>
	{#snippet conversationView(conversation: DirectConversation)}<DirectMessages
			{conversation}
			presentation="inbox"
			onread={() => void refresh()}
		/>{/snippet}
	{#snippet composeView()}
		<div class="compose-view">
			<button
				class="compose-back"
				onclick={() => {
					composing = false;
					query = '';
				}}><ArrowLeft size={16} /> Cancel</button
			>
			<h2>{composeKind === 'group' ? 'Bring your people together.' : 'Say hello.'}</h2>
			<p>
				{composeKind === 'group'
					? 'Choose a name and at least two people. Only participants can see this conversation.'
					: 'Find someone in your communities to start a conversation.'}
			</p>
			{#if composeKind === 'group'}
				<label class="group-name"
					>Group name<input
						aria-label="Group name"
						maxlength={100}
						placeholder="e.g. Thursday study crew"
						bind:value={groupName}
					/></label
				>
				<div class="selected-people">
					{#each groupPeople as person (JSON.stringify(person.target))}<button
							aria-label={'Remove ' + person.name}
							onclick={() => (groupPeople = groupPeople.filter((item) => item !== person))}
							>{person.name}<X size={13} /></button
						>{/each}
				</div>
			{/if}
			<label class="recipient-search"
				><Search size={18} /><input
					bind:this={recipientInput}
					aria-label="Find a recipient"
					placeholder="Search by name…"
					bind:value={query}
				/></label
			>
			<p role="status">
				{peopleStatus || (query.trim().length < 2 ? 'Type at least two letters.' : '')}
			</p>
			{#each people as person (person.community_id + JSON.stringify(person.target))}<button
					class="person-result"
					disabled={composeKind === 'group' &&
						(groupPeople.length >= 19 ||
							groupPeople.some(
								(item) => JSON.stringify(item.target) === JSON.stringify(person.target)
							))}
					onclick={() => (composeKind === 'group' ? addPerson(person) : void start(person))}
					><strong>{person.name}</strong><span>{person.community}</span></button
				>{/each}
			{#if composeKind === 'group'}<div class="group-actions">
					<span>{groupPeople.length} of 19 people selected</span><button
						disabled={creatingGroup || groupPeople.length < 2 || !groupName.trim()}
						onclick={() => void createGroup()}
						>{creatingGroup ? 'Creating…' : 'Create private group'}</button
					>
				</div>{/if}
		</div>
	{/snippet}
	<MessagesInbox
		{conversations}
		{selected}
		{composing}
		{composeView}
		{conversationView}
		{loading}
		{error}
		{theme}
		backLabel={returnLabel}
		ontheme={toggleTheme}
		onconversationaction={conversationAction}
		onselect={choose}
		onback={backToCommunity}
		onnew={() => void newConversation('direct')}
		onnewgroup={() => void newConversation('group')}
	/>
</main>

<style>
	.person-result:disabled {
		opacity: 0.45;
		cursor: default;
	}
	.group-name {
		display: grid;
		gap: 8px;
		margin-top: 28px;
		font-size: 12px;
		color: var(--muted);
	}
	.group-name input {
		min-width: 0;
		width: 100%;
		height: 46px;
		border: 1px solid var(--line);
		border-radius: 10px;
		padding-inline: 14px;
		background: transparent;
		font: inherit;
		font-size: 16px;
	}
	.selected-people {
		display: flex;
		flex-wrap: wrap;
		gap: 6px;
		margin-top: 16px;
	}
	.selected-people button {
		display: flex;
		align-items: center;
		gap: 8px;
		padding: 8px 10px;
		border: 1px solid var(--line);
		border-radius: 20px;
		background: var(--well);
		color: var(--ink);
		font-size: 12px;
		cursor: pointer;
	}
	.group-actions {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 12px;
		flex-wrap: wrap;
		margin-top: 32px;
	}
	.group-actions span {
		font-size: 12px;
		color: var(--muted);
	}
	.group-actions button {
		padding: 12px 16px;
		border: 0;
		border-radius: 10px;
		background: var(--ink);
		color: var(--panel);
		font-size: 13px;
		cursor: pointer;
	}
	.group-actions button:disabled {
		opacity: 0.4;
		cursor: default;
	}

	.site-navigation {
		padding-inline: clamp(10px, 3vw, 40px);
		background: white;
	}
	.site-navigation[data-theme='dark'] {
		background: #20211d;
	}
	.messages-screen {
		height: calc(100dvh - var(--site-header-height));
		overflow: hidden;
	}
	.compose-view {
		padding: clamp(20px, 4vw, 48px);
		overflow-y: auto;
	}
	.compose-view h2 {
		font-size: 28px;
		font-weight: 500;
		letter-spacing: -0.04em;
		margin: 32px 0 8px;
	}
	.compose-view p {
		color: var(--muted);
		font-size: 13px;
		line-height: 1.6;
	}
	.compose-back {
		display: inline-flex;
		align-items: center;
		gap: 8px;
		background: transparent;
		border: 0;
		color: var(--muted);
		cursor: pointer;
	}
	.recipient-search {
		display: flex;
		align-items: center;
		gap: 12px;
		border: 1px solid var(--line);
		border-radius: 12px;
		padding: 0 14px;
		margin-top: 28px;
	}
	.recipient-search input {
		width: 100%;
		min-width: 0;
		height: 48px;
		font: inherit;
		font-size: 16px;
		border: 0;
		background: transparent;
	}
	.person-result {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 16px;
		width: 100%;
		padding: 14px;
		background: var(--panel);
		color: var(--ink);
		border: 1px solid var(--line);
		border-radius: 10px;
		margin-top: 8px;
		text-align: left;
		cursor: pointer;
		overflow-wrap: anywhere;
	}
	.person-result span {
		font-size: 12px;
		color: var(--muted);
	}
</style>
