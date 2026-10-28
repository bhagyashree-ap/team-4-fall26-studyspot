<script lang="ts">
	import { base, resolve } from '$app/paths';
	import { onMount, tick } from 'svelte';
	import SiteHeader from '$lib/SiteHeader.svelte';
	import Autocomplete from '$lib/Autocomplete.svelte';
	import ChannelChat from '$lib/ChannelChat.svelte';
	import DirectMessages from '$lib/DirectMessages.svelte';
	import {
		communityRequest,
		type Channel,
		type Community,
		type DirectConversation,
		type GuestMember,
		type Invite,
		type Member
	} from '$lib/communities';
	import { session } from '$lib/session.svelte';

	let communities = $state<Community[]>([]);
	let selected = $state<Community | null>(null);
	let directConversations = $state<DirectConversation[]>([]);
	let selectedDM = $state<DirectConversation | null>(null);
	let members = $state<Member[]>([]);
	let guestMembers = $state<GuestMember[]>([]);
	let memberOffset = 0;
	let memberRequest = 0;
	let hasMoreMembers = $state(false);
	let membersLoading = $state(false);
	let guestCount = $state(0);
	let invites = $state<Invite[]>([]);
	let detailsStatus = $state('');
	let detailsSaving = false;
	let channelStatus = $state('');
	let channelSaving = $state(false);
	let query = $state('');
	let viewMine = $state(false);
	let hasMore = $state(false);
	let error = $state('');
	let loading = $state(true);
	let creating = $state(false);
	let name = $state('');
	let description = $state('');
	let school = $state('');
	let course = $state('');
	let schools = $state<string[]>([]);
	let schoolsRequested = false;
	const popularSchools = [
		'New York University',
		'CUNY Hunter College',
		'CUNY Queens College',
		'Columbia University in the City of New York',
		'Cornell University',
		'Harvard University',
		'Massachusetts Institute of Technology',
		'Stanford University',
		'University of California-Berkeley',
		'University of California-Los Angeles',
		'University of Michigan-Ann Arbor'
	];
	const popularCourses = [
		'Calculus I',
		'Calculus II',
		'Linear Algebra',
		'Introduction to Statistics',
		'Introduction to Computer Science',
		'Data Structures',
		'General Biology',
		'General Chemistry',
		'Physics I',
		'Introduction to Psychology',
		'Microeconomics',
		'English Composition'
	];
	let courseOptions = $derived([
		...new Set([
			...communities
				.filter((community) => community.school === school && community.course)
				.map((community) => community.course),
			...popularCourses
		])
	]);
	let transferableMembers = $derived(
		members.filter((member) => member.user_id !== String(selected?.owner_id))
	);
	let channelName = $state('');
	let channelCreateOpen = $state(false);
	let channelMenuOpen = $state<number | null>(null);
	let editingChannelId = $state<number | null>(null);
	let renameValue = $state('');
	let deleteTarget = $state<Channel | null>(null);
	let channelNameInput = $state<HTMLInputElement>();
	let renameInput = $state<HTMLInputElement>();
	let deleteDialog = $state<HTMLDialogElement>();
	let activeChannelId = $state<number | null>(null);
	let inviteLink = $state('');
	let shareLink = $state('');
	let copyStatus = $state('');
	let tab = $state<'main' | 'members' | 'settings'>('main');
	let requestNumber = 0;
	const activeCommunityId = () => selected?.id;

	const palette = ['#9b1c3a', '#eb459e', '#3ba55c', '#faa61a', '#9b59b6', '#1abc9c', '#e67e22'];
	function avatarColor(name: string): string {
		let h = 0;
		for (const c of name) h = (h * 31 + c.charCodeAt(0)) | 0;
		return palette[Math.abs(h) % palette.length];
	}
	function initials(name: string): string {
		return (
			name
				.split(/\s+/)
				.slice(0, 2)
				.map((w) => w[0] ?? '')
				.join('')
				.toUpperCase() || '?'
		);
	}

	async function loadSchools() {
		if (schoolsRequested) return;
		schoolsRequested = true;
		try {
			const response = await fetch(`${base}/schools.json`);
			if (!response.ok) throw new Error('School suggestions are unavailable.');
			schools = await response.json();
		} catch {
			schoolsRequested = false;
		}
	}

	async function browse(search = query, more = false, mine = viewMine) {
		const current = ++requestNumber;
		loading = true;
		try {
			const result = await communityRequest<{ items: Community[]; has_more: boolean }>(
				`/communities?q=${encodeURIComponent(search)}&offset=${more ? communities.length : 0}${mine ? '&mine=true' : ''}`
			);
			if (current === requestNumber) {
				communities = more ? [...communities, ...result.items] : result.items;
				hasMore = result.has_more;
				error = '';
			}
		} catch (cause) {
			if (current === requestNumber) {
				communities = [];
				hasMore = false;
				error = message(cause);
			}
		} finally {
			if (current === requestNumber) loading = false;
		}
	}

	function message(cause: unknown): string {
		return cause instanceof Error ? cause.message : 'Something went wrong.';
	}

	async function choose(id: number, channelId?: number | null) {
		error = '';
		try {
			selected = await communityRequest<Community>(`/communities/${id}`);
			selectedDM = null;
			channelCreateOpen = false;
			channelMenuOpen = null;
			editingChannelId = null;
			shareLink = '';
			copyStatus = '';
			activeChannelId =
				selected.channels?.find((channel) => channel.id === channelId)?.id ??
				selected.channels?.[0]?.id ??
				null;
			name = selected.name;
			description = selected.description;
			school = selected.school;
			course = selected.course;
			detailsStatus = '';
			channelStatus = '';
			members = [];
			guestMembers = [];
			memberOffset = 0;
			hasMoreMembers = false;
			guestCount = 0;
			invites = [];
			tab = 'main';
			history.replaceState(
				null,
				'',
				`?id=${id}${activeChannelId ? `&channel=${activeChannelId}` : ''}`
			);
			void loadMembers();
		} catch (cause) {
			error = message(cause);
		}
	}

	async function loadDMs(): Promise<DirectConversation[]> {
		try {
			directConversations = (await communityRequest<{ items: DirectConversation[] }>('/dms')).items;
			return directConversations;
		} catch (cause) {
			error = message(cause);
			return [];
		}
	}

	function openDM(conversation: DirectConversation) {
		selectedDM = conversation;
		selected = null;
		creating = false;
		history.replaceState(null, '', `?dm=${conversation.id}`);
		void loadDMs();
	}

	function goHome() {
		selected = null;
		selectedDM = null;
		creating = false;
		history.replaceState(null, '', resolve('/communities'));
	}

	function showCreate() {
		goHome();
		creating = true;
		name = description = school = course = '';
	}

	async function startMemberDM(userId: string) {
		if (!selected) return;
		try {
			openDM(
				await communityRequest<DirectConversation>(`/communities/${selected.id}/dms`, 'POST', {
					user_id: userId
				})
			);
		} catch (cause) {
			error = message(cause);
		}
	}

	async function startGuestDM(guestMemberId: number) {
		if (!selected) return;
		try {
			openDM(
				await communityRequest<DirectConversation>(`/communities/${selected.id}/dms`, 'POST', {
					guest_member_id: guestMemberId
				})
			);
		} catch (cause) {
			error = message(cause);
		}
	}

	async function action(path: string, method = 'POST', body?: object) {
		error = '';
		try {
			await communityRequest(path, method, body);
			const previousTab = tab;
			const previousChannelId = activeChannelId;
			if (selected) {
				await choose(selected.id, previousChannelId);
				if (selected?.channels?.some((channel) => channel.id === previousChannelId))
					activeChannelId = previousChannelId;
				if (previousTab === 'members') {
					tab = 'members';
					await loadMembers();
				}
				if (previousTab === 'settings') await loadSettings();
			}
			await browse();
		} catch (cause) {
			error = message(cause);
		}
	}

	function selectChannel(channelId: number) {
		activeChannelId = channelId;
		channelMenuOpen = null;
		editingChannelId = null;
		shareLink = '';
		copyStatus = '';
		if (selected) history.replaceState(null, '', `?id=${selected.id}&channel=${channelId}`);
	}

	async function createChannel() {
		if (!selected) return;
		try {
			const created = await communityRequest<Channel>(
				`/communities/${selected.id}/channels`,
				'POST',
				{ name: channelName }
			);
			channelName = '';
			await choose(selected.id, created.id);
			await tick();
			document.getElementById(`channel-select-${created.id}`)?.focus();
		} catch (cause) {
			error = message(cause);
		}
	}

	async function openChannelCreate() {
		channelMenuOpen = null;
		channelCreateOpen = true;
		await tick();
		channelNameInput?.focus();
	}

	async function closeChannelCreate() {
		channelCreateOpen = false;
		await tick();
		document.getElementById('add-channel-button')?.focus();
	}

	async function toggleChannelMenu(channelId: number) {
		channelMenuOpen = channelMenuOpen === channelId ? null : channelId;
		if (channelMenuOpen !== null) {
			await tick();
			document.querySelector<HTMLButtonElement>(`#channel-options-${channelId} button`)?.focus();
		}
	}

	async function startChannelRename(channel: Channel) {
		selectChannel(channel.id);
		editingChannelId = channel.id;
		renameValue = channel.name;
		channelStatus = '';
		await tick();
		renameInput?.focus();
	}

	async function cancelChannelRename(channelId: number) {
		editingChannelId = null;
		await tick();
		(
			document.getElementById(`edit-channel-${channelId}`) ??
			document.getElementById(`channel-trigger-${channelId}`)
		)?.focus();
	}

	async function saveChannelName() {
		if (channelSaving || !selected || editingChannelId === null) return;
		const communityId = selected.id;
		const channelId = editingChannelId;
		channelSaving = true;
		try {
			while (selected?.id === communityId && editingChannelId === channelId) {
				const current = selected.channels?.find((channel) => channel.id === channelId);
				const draft = renameValue.trim();
				if (!current || draft === current.name || !/^[a-z0-9][a-z0-9-]{0,49}$/.test(draft)) break;
				channelStatus = 'Saving…';
				const saved: Channel = await communityRequest<Channel>(
					`/communities/${communityId}/channels/${channelId}`,
					'PATCH',
					{ name: draft }
				);
				if (selected?.id !== communityId) break;
				selected = {
					...selected,
					channels: selected.channels?.map((channel) =>
						channel.id === channelId ? saved : channel
					)
				};
				channelStatus = renameValue.trim() === draft ? 'Saved' : 'Unsaved changes';
			}
		} catch (cause) {
			channelStatus = `Could not save: ${message(cause)}`;
		} finally {
			channelSaving = false;
		}
	}

	async function finishChannelEdit(channelId: number) {
		await saveChannelName();
		if (channelStatus.startsWith('Could not save')) return;
		await cancelChannelRename(channelId);
	}

	async function saveDetails() {
		if (detailsSaving || !selected || selected.role !== 'owner' || !name.trim()) return;
		const communityId = selected.id;
		detailsSaving = true;
		try {
			while (selected?.id === communityId) {
				const draft = { name: name.trim(), description, school, course };
				if (
					Object.entries(draft).every(
						([key, value]) => selected?.[key as keyof Community] === value
					)
				)
					break;
				detailsStatus = 'Saving…';
				const saved: Community = await communityRequest<Community>(
					`/communities/${communityId}`,
					'PATCH',
					draft
				);
				if (selected?.id !== communityId) break;
				selected = { ...selected, ...saved };
				detailsStatus = 'Saved';
			}
			if (selected?.id === communityId) await browse();
		} catch (cause) {
			detailsStatus = `Could not save: ${message(cause)}`;
		} finally {
			detailsSaving = false;
		}
	}

	async function updateChannel(channelId: number, changes: object) {
		await action(`/communities/${activeCommunityId()}/channels/${channelId}`, 'PATCH', changes);
		await tick();
		document.getElementById(`channel-trigger-${channelId}`)?.focus();
	}

	async function confirmChannelDelete(channel: Channel) {
		channelMenuOpen = null;
		deleteTarget = channel;
		await tick();
		deleteDialog?.showModal();
	}

	async function deleteChannel() {
		if (!selected || !deleteTarget) return;
		const channelId = deleteTarget.id;
		deleteDialog?.close();
		deleteTarget = null;
		await action(`/communities/${selected.id}/channels/${channelId}`, 'DELETE');
		await tick();
		if (activeChannelId) document.getElementById(`channel-select-${activeChannelId}`)?.focus();
	}

	async function closeDeleteDialog() {
		const channelId = deleteTarget?.id;
		deleteTarget = null;
		await tick();
		if (channelId) document.getElementById(`channel-trigger-${channelId}`)?.focus();
	}

	function handleEscape(event: KeyboardEvent) {
		if (event.key !== 'Escape' || deleteDialog?.open) return;
		if (channelMenuOpen !== null) {
			const channelId = channelMenuOpen;
			channelMenuOpen = null;
			void tick().then(() => document.getElementById(`channel-trigger-${channelId}`)?.focus());
		} else if (editingChannelId !== null) void cancelChannelRename(editingChannelId);
		else if (channelCreateOpen) void closeChannelCreate();
	}

	async function shareChannel() {
		if (!selected || !activeChannelId) return;
		shareLink = `${location.origin}${resolve('/communities')}?id=${selected.id}&channel=${activeChannelId}`;
		try {
			await navigator.clipboard.writeText(shareLink);
			copyStatus = 'Link copied! Anyone can use it to join this community.';
		} catch {
			copyStatus = 'Select and copy the link below to share this channel.';
		}
	}

	async function deleteCommunity() {
		if (!selected || !confirm(`Delete ${selected.name} and all its channels?`)) return;
		try {
			await communityRequest(`/communities/${selected.id}`, 'DELETE');
			selected = null;
			history.replaceState(null, '', resolve('/communities'));
			await browse();
		} catch (cause) {
			error = message(cause);
		}
	}

	async function create() {
		error = '';
		try {
			const created = await communityRequest<Community>('/communities', 'POST', {
				name,
				description,
				school,
				course
			});
			creating = false;
			name = description = school = course = '';
			await browse();
			await choose(created.id);
		} catch (cause) {
			error = message(cause);
		}
	}

	async function loadMembers(more = false) {
		if (!selected) return;
		if (more && membersLoading) return;
		const current = ++memberRequest;
		const communityId = selected.id;
		const offset = more ? memberOffset : 0;
		membersLoading = true;
		try {
			const result = await communityRequest<{
				items: Member[];
				has_more: boolean;
				guest_items: GuestMember[];
				guest_has_more: boolean;
				guest_count: number;
			}>(`/communities/${communityId}/members?limit=50&offset=${offset}`);
			if (selected?.id !== communityId || current !== memberRequest) return;
			members = more ? [...members, ...result.items] : result.items;
			guestMembers = more ? [...guestMembers, ...result.guest_items] : result.guest_items;
			memberOffset = offset + 50;
			hasMoreMembers = result.has_more || result.guest_has_more;
			guestCount = result.guest_count;
			error = '';
		} catch (cause) {
			if (selected?.id === communityId && current === memberRequest) error = message(cause);
		} finally {
			if (selected?.id === communityId && current === memberRequest) membersLoading = false;
		}
	}

	async function loadSettings() {
		if (!selected) return;
		tab = 'settings';
		if (selected.role === 'owner' || selected.role === 'moderator') {
			try {
				invites = await communityRequest<Invite[]>(`/communities/${selected.id}/invites`);
			} catch (cause) {
				error = message(cause);
			}
		}
	}

	$effect(() => {
		const communityId = selected?.id;
		const draft = { name, description, school, course };
		if (
			!communityId ||
			selected?.role !== 'owner' ||
			!draft.name.trim() ||
			Object.entries(draft).every(([key, value]) => selected?.[key as keyof Community] === value)
		)
			return;
		const timer = window.setTimeout(() => void saveDetails(), 650);
		return () => window.clearTimeout(timer);
	});

	$effect(() => {
		const channel = selected?.channels?.find((item) => item.id === editingChannelId);
		const draft = renameValue.trim();
		if (!channel || channel.name === draft || !/^[a-z0-9][a-z0-9-]{0,49}$/.test(draft)) return;
		const timer = window.setTimeout(() => void saveChannelName(), 650);
		return () => window.clearTimeout(timer);
	});

	async function createInvite() {
		if (!selected) return;
		try {
			const result = await communityRequest<{ token: string }>(
				`/communities/${selected.id}/invites`,
				'POST',
				{ expires_in_hours: 168, max_uses: 100 }
			);
			inviteLink = `${location.origin}${resolve('/communities')}?invite=${result.token}`;
			await loadSettings();
		} catch (cause) {
			error = message(cause);
		}
	}

	$effect(() => {
		if (session.status !== 'signed-in') return;
		void browse(query, false, viewMine);
	});

	onMount(() => {
		const dmId = Number(new URL(location.href).searchParams.get('dm'));
		void session.start().then(async () => {
			if (session.status === 'signed-out') {
				session.logIn(location.pathname + location.search);
				return;
			}
			if (session.status === 'disabled' || session.status === 'error') {
				return;
			}
			if (selected) void choose(selected.id, activeChannelId);
			const items = await loadDMs();
			const conversation = items.find((item) => item.id === dmId);
			if (conversation) openDM(conversation);
		});
		const url = new URL(location.href);
		const id = Number(url.searchParams.get('id'));
		const channelId = Number(url.searchParams.get('channel'));
		const requestedChannel = Number.isSafeInteger(channelId) && channelId > 0 ? channelId : null;
		if (Number.isSafeInteger(id) && id > 0) void choose(id, requestedChannel);
		const token = url.searchParams.get('invite');
		if (token) {
			void communityRequest<{ community_id: number }>(
				`/communities/invites/${encodeURIComponent(token)}/redeem`,
				'POST'
			)
				.then((result) => choose(result.community_id, requestedChannel))
				.catch((cause) => {
					error = message(cause);
				});
		}
	});
</script>

<svelte:window onkeydown={handleEscape} />

<svelte:head>
	<title>Communities · StudySpot</title>
	<meta name="description" content="Find and create public study communities." />
</svelte:head>

<div class="shell">
	<SiteHeader />

	{#if session.status === 'loading'}
		<div class="auth-loading" aria-label="Loading…">
			<span class="auth-spinner" aria-hidden="true"></span>
		</div>
	{:else if session.status === 'signed-out' || session.status === 'disabled' || session.status === 'error'}
		<!-- redirect fires in onMount; show nothing while it happens -->
	{:else}

	<dialog
		bind:this={deleteDialog}
		class="confirm-dialog"
		aria-labelledby="delete-channel-title"
		aria-describedby="delete-channel-description"
		onclose={() => void closeDeleteDialog()}
	>
		{#if deleteTarget}
			<h2 id="delete-channel-title">Delete #{deleteTarget.name}?</h2>
			<p id="delete-channel-description">
				This removes the channel and all its messages for everyone in the community.
			</p>
			<div class="form-actions">
				<button onclick={() => deleteDialog?.close()}>Cancel</button>
				<button class="btn-danger" onclick={() => void deleteChannel()}>Delete channel</button>
			</div>
		{/if}
	</dialog>

	<main>
		<!-- ── Left sidebar ── -->
		<aside class="sidebar">
			<div class="sidebar-top">
				<button class="home-link" onclick={goHome}>Communities</button>
				<div class="sidebar-search-row">
					<input
						id="community-search"
						bind:value={query}
						placeholder="Search communities…"
					/>
				</div>
				<div class="sidebar-tabs">
					<button class:chosen={!viewMine} onclick={() => (viewMine = false)}>All</button
					><button class:chosen={viewMine} onclick={() => (viewMine = true)}>Mine</button>
				</div>
			</div>

			{#if loading}<p class="sidebar-muted">Loading…</p>{/if}

			<div class="sidebar-section-label">Communities</div>
			<div class="sidebar-list">
				{#each communities as community (community.id)}
					<button
						class="sidebar-item"
						class:active={selected?.id === community.id}
						aria-current={selected?.id === community.id ? 'page' : undefined}
						onclick={() => void choose(community.id)}
					>
						<div class="sidebar-item-icon" style="background:{avatarColor(community.name)}">
							{initials(community.name)}
						</div>
						<div class="sidebar-item-text">
							<span class="sidebar-item-name">{community.name}</span>
							<span class="sidebar-item-meta">{community.member_count} {community.member_count === 1 ? 'member' : 'members'}</span>
						</div>
					</button>
				{/each}
			</div>
			{#if hasMore}
				<button class="sidebar-load-more" onclick={() => void browse(query, true)}>Show more</button>
			{/if}

			{#if directConversations.length}
				<div class="sidebar-section-label">Direct Messages</div>
				<div class="sidebar-list">
					{#each directConversations as conversation (conversation.id)}
						<button
							class="sidebar-item"
							class:active={selectedDM?.id === conversation.id}
							aria-current={selectedDM?.id === conversation.id ? 'page' : undefined}
							onclick={() => openDM(conversation)}
						>
							<div class="sidebar-item-avatar" style="background:{avatarColor(conversation.other_name)}">
								{initials(conversation.other_name)}
							</div>
							<div class="sidebar-item-text">
								<span class="sidebar-item-name">{conversation.other_name}</span>
								<span class="sidebar-item-meta">Direct message</span>
							</div>
						</button>
					{/each}
				</div>
			{/if}

			<div class="sidebar-bottom">
				<button class="create-btn" onclick={showCreate}>
					+ New community
				</button>
			</div>
		</aside>

		<!-- ── Main content ── -->
		<div class="content" class:workspace-mode={!!selected}>
			{#if error}<p class="error-banner" role="alert">{error}</p>{/if}

			{#if creating}
				<!-- Create form -->
				<div class="form-page">
					<div class="form-page-inner">
						<p class="form-eyebrow">StudySpot Communities</p>
						<h2>Create a community</h2>
						<p class="form-lead">Start a public study group for your class or course.</p>
						<form
							onsubmit={(event) => {
								event.preventDefault();
								void create();
							}}
						>
							<label>
								<span>Name</span>
								<input required maxlength="100" bind:value={name} placeholder="Math 51A Study Group" />
							</label>
							<label>
								<span>Description</span>
								<textarea maxlength="1000" bind:value={description}></textarea>
							</label>
							<Autocomplete
								id="create-school"
								label="School"
								bind:value={school}
								options={schools}
								popular={popularSchools}
								placeholder="Search US schools"
								help="Choose a school or type another name."
								onOpen={() => void loadSchools()}
							/>
							<Autocomplete
								id="create-course"
								label="Course"
								bind:value={course}
								options={courseOptions}
								popular={courseOptions}
								placeholder="Search courses or enter a code"
								help="Course codes vary by school; you can enter yours."
							/>
							<div class="form-actions">
								<button class="btn-primary">Create community</button>
								<button type="button" onclick={goHome}>Cancel</button>
							</div>
						</form>
					</div>
				</div>

			{:else if selectedDM}
				<DirectMessages conversation={selectedDM} />

			{:else if selected}
				<!-- Community workspace -->
				<div class="workspace">

					<!-- Channel rail (left) -->
					<nav class="channel-rail" aria-label={`Channels in ${selected.name}`}>
						<div class="community-header">
							<div class="community-avatar" style="background:{avatarColor(selected.name)}" aria-hidden="true">
								{initials(selected.name)}
							</div>
							<div class="community-header-text">
								<span class="community-name">{selected.name}</span>
								<span class="community-meta">{selected.member_count} members</span>
							</div>
						</div>

						<div class="rail-section">
							<div class="rail-section-header">
								<span>CHANNELS</span>
								{#if selected.role === 'owner'}
									<button
										class="rail-add-btn"
										id="add-channel-button"
										aria-label="Add channel"
										title={(selected.channels?.length ?? 0) >= 20 ? 'Channel limit reached' : 'Add channel'}
										disabled={(selected.channels?.length ?? 0) >= 20}
										onclick={() => void openChannelCreate()}
									>+</button>
								{/if}
							</div>

							{#if channelCreateOpen}
								<form
									class="channel-create-form"
									onsubmit={(event) => {
										event.preventDefault();
										void createChannel();
									}}
								>
									<input
										id="new-channel-name"
										bind:this={channelNameInput}
										required
										pattern="[a-z0-9][a-z0-9-]*"
										maxlength="50"
										bind:value={channelName}
										placeholder="channel-name"
									/>
									<p class="channel-name-hint">Lowercase, numbers, hyphens only.</p>
									<div class="mini-actions">
										<button class="btn-sm-primary">Create</button>
										<button type="button" onclick={() => void closeChannelCreate()}>Cancel</button>
									</div>
								</form>
							{/if}

							<ul class="channel-list">
								{#each selected.channels ?? [] as channel (channel.id)}
									<li class="channel-item">
										<div
											class="channel-row"
											class:active={activeChannelId === channel.id}
											class:archived={channel.archived}
										>
											<button
												class="channel-btn"
												id={`channel-select-${channel.id}`}
												aria-current={activeChannelId === channel.id ? 'page' : undefined}
												onclick={() => selectChannel(channel.id)}
											>
												<span class="ch-hash" aria-hidden="true">#</span>
												<span class="ch-name">{channel.name}</span>
												{#if channel.archived}<span class="archived-chip">archived</span>{/if}
											</button>
											{#if selected.role === 'owner'}
												<button
													class="ch-options-btn"
													id={`channel-trigger-${channel.id}`}
													aria-label={`Options for #${channel.name}`}
													aria-expanded={channelMenuOpen === channel.id}
													aria-controls={`channel-options-${channel.id}`}
													onclick={() => void toggleChannelMenu(channel.id)}
												>⋯</button>
											{/if}
										</div>
										{#if channelMenuOpen === channel.id}
											<div
												class="channel-menu"
												id={`channel-options-${channel.id}`}
												role="group"
												aria-label={`Options for #${channel.name}`}
											>
												<button onclick={() => void startChannelRename(channel)}>✏ Rename</button>
												<button
													disabled={channel.position === 0}
													onclick={() => void updateChannel(channel.id, { position: channel.position - 1 })}
												>↑ Move up</button>
												<button
													disabled={channel.position >= (selected.channels?.length ?? 0) - 1}
													onclick={() => void updateChannel(channel.id, { position: channel.position + 1 })}
												>↓ Move down</button>
												<button onclick={() => void updateChannel(channel.id, { archived: !channel.archived })}>
													{channel.archived ? '↩ Restore' : '📦 Archive'}
												</button>
												<button
													class="menu-danger"
													onclick={() => void confirmChannelDelete(channel)}
												>🗑 Delete</button>
											</div>
										{/if}
									</li>
								{/each}
							</ul>
						</div>

						<!-- Community action buttons at bottom of rail -->
						<div class="rail-actions">
							{#if selected.role === 'visitor'}
								<button class="rail-join-btn" onclick={() => void action(`/communities/${activeCommunityId()}/join`)}>
									Join community
								</button>
							{:else if selected.role !== 'owner'}
								<button class="rail-leave-btn" onclick={() => void action(`/communities/${activeCommunityId()}/leave`)}>
									Leave community
								</button>
							{/if}
						</div>
					</nav>

					<!-- Chat area (center) -->
					<div class="chat-area">
						{#each selected.channels?.filter((ch) => ch.id === activeChannelId) ?? [] as channel (channel.id)}
							<div class="channel-pane">
								{#if editingChannelId === channel.id}
									<div class="channel-edit-bar">
										<form
											onsubmit={(e) => { e.preventDefault(); void finishChannelEdit(channel.id); }}
										>
											<label for={`rename-channel-${channel.id}`}>Rename #</label>
											<input
												id={`rename-channel-${channel.id}`}
												bind:this={renameInput}
												required
												pattern="[a-z0-9][a-z0-9-]*"
												maxlength="50"
												bind:value={renameValue}
												aria-describedby={`rename-status-${channel.id}`}
											/>
											<span id={`rename-status-${channel.id}`} class="save-hint" role="status">
												{channelStatus || 'Saves automatically'}
											</span>
											<div class="mini-actions">
												<button class="btn-sm-primary" disabled={channelSaving}>Done</button>
												<button type="button" onclick={() => void cancelChannelRename(channel.id)}>Close</button>
												<button type="button" onclick={() => void updateChannel(channel.id, { archived: !channel.archived })}>
													{channel.archived ? 'Restore' : 'Archive'}
												</button>
												<button type="button" class="btn-danger-sm" onclick={() => void confirmChannelDelete(channel)}>Delete</button>
											</div>
										</form>
									</div>
								{/if}

								{#if copyStatus || shareLink}
									<div class="share-banner">
										{#if copyStatus}<p class="share-msg">{copyStatus}</p>{/if}
										{#if shareLink}
											<input
												class="share-link"
												readonly
												aria-label="Channel share link"
												value={shareLink}
												onclick={(e) => e.currentTarget.select()}
											/>
										{/if}
									</div>
								{/if}

								{#if selected.role === 'visitor'}
									<div class="join-wall">
										<div class="join-wall-icon" aria-hidden="true" style="background:{avatarColor(channel.name)}">#</div>
										<h3>Join to participate</h3>
										<p>Join this community to read and send messages in #{channel.name}.</p>
										<button class="btn-primary" onclick={() => void action(`/communities/${activeCommunityId()}/join`)}>
											Join community
										</button>
									</div>
								{:else}
									<ChannelChat
										communityId={selected.id}
										{channel}
										role={selected.role}
										onDirectMessage={openDM}
									/>
								{/if}
							</div>
						{:else}
							<div class="empty-channel">
								<div class="empty-icon" aria-hidden="true">#</div>
								<h3>No channels yet</h3>
								<p>Create a channel to start organizing conversations.</p>
								{#if selected.role === 'owner'}
									<button class="btn-primary" onclick={() => void openChannelCreate()}>Add channel</button>
								{/if}
							</div>
						{/each}
					</div>

					<!-- Members rail (right) -->
					<aside class="member-rail" aria-label={`Members of ${selected.name}`}>
						<!-- Tab header -->
						<div class="member-rail-header">
							<button
								class="tab-link"
								class:chosen={tab === 'main'}
								onclick={() => (tab = 'main')}
							>Chat</button>
							<button
								class="tab-link"
								class:chosen={tab === 'members'}
								onclick={() => { tab = 'members'; void loadMembers(); }}
							>Members</button>
							{#if selected.role === 'owner' || selected.role === 'moderator'}
								<button
									class="tab-link"
									class:chosen={tab === 'settings'}
									onclick={() => void loadSettings()}
								>Manage</button>
							{/if}
						</div>

						{#if tab === 'main'}
							<!-- Members sidebar list -->
							<div class="rail-members-label">Members · {selected.member_count}</div>
							{#if membersLoading && !members.length}<p class="rail-muted">Loading…</p>{/if}
							{#each members as member (member.user_id)}
								<div class="member-card">
									<div class="member-avatar" style="background:{avatarColor(member.display_name)}">
										{initials(member.display_name)}
									</div>
									<div class="member-info">
										<strong>{member.is_me ? 'You' : member.display_name}</strong>
										<span>{member.user_id === String(selected.owner_id) ? 'Owner' : member.role}</span>
									</div>
									{#if !member.is_me && selected.role !== 'visitor'}
										<button class="dm-btn" title="Send DM" onclick={() => void startMemberDM(member.user_id)}>✉</button>
									{/if}
								</div>
							{/each}
							{#each guestMembers as guest (guest.id)}
								<div class="member-card">
									<div class="member-avatar" style="background:{avatarColor(guest.display_name)}">
										{initials(guest.display_name)}
									</div>
									<div class="member-info">
										<strong>{guest.is_me ? 'You' : guest.display_name}</strong>
										<span>{guest.role === 'owner' ? 'Owner' : 'Guest'}</span>
									</div>
									{#if !guest.is_me && selected.role !== 'visitor'}
										<button class="dm-btn" title="Send DM" onclick={() => void startGuestDM(guest.id)}>✉</button>
									{/if}
								</div>
							{/each}
							{#if hasMoreMembers}
								<button class="load-more-members" onclick={() => void loadMembers(true)}>Show more members</button>
							{/if}

						{:else if tab === 'members'}
							<!-- Full members list -->
							<div class="rail-members-label">All members · {selected.member_count}</div>
							<p class="rail-muted">{guestCount} guest {guestCount === 1 ? 'member' : 'members'}</p>
							{#if membersLoading && !members.length}<p class="rail-muted">Loading…</p>{/if}
							{#each members as member (member.user_id)}
								<div class="member-card">
									<div class="member-avatar" style="background:{avatarColor(member.display_name)}">
										{initials(member.display_name)}
									</div>
									<div class="member-info">
										<strong>{member.is_me ? 'You' : member.display_name}</strong>
										<span>{member.user_id === String(selected.owner_id) ? 'Owner' : member.role}</span>
									</div>
									<div class="member-actions">
										{#if !member.is_me && selected.role !== 'visitor'}
											<button class="action-chip" onclick={() => void startMemberDM(member.user_id)}>DM</button>
										{/if}
										{#if selected.role === 'owner' && member.user_id !== String(selected.owner_id)}
											<button
												class="action-chip"
												onclick={() => void action(`/communities/${activeCommunityId()}/members/${member.user_id}`, 'PATCH', { role: member.role === 'moderator' ? 'member' : 'moderator' })}
											>{member.role === 'moderator' ? 'Demote' : 'Mod'}</button>
										{/if}
										{#if (selected.role === 'owner' || selected.role === 'moderator') && member.user_id !== String(selected.owner_id) && (member.role !== 'moderator' || selected.role === 'owner')}
											<button class="action-chip danger" onclick={() => void action(`/communities/${activeCommunityId()}/members/${member.user_id}`, 'DELETE')}>Kick</button>
											<button class="action-chip danger" onclick={() => void action(`/communities/${activeCommunityId()}/moderation`, 'POST', { user_id: member.user_id, action: 'ban' })}>Ban</button>
										{/if}
									</div>
								</div>
							{/each}
							{#each guestMembers as guest (guest.id)}
								<div class="member-card">
									<div class="member-avatar" style="background:{avatarColor(guest.display_name)}">
										{initials(guest.display_name)}
									</div>
									<div class="member-info">
										<strong>{guest.is_me ? 'You' : guest.display_name}</strong>
										<span>{guest.role === 'owner' ? 'Owner' : 'Guest'}</span>
									</div>
									{#if !guest.is_me && selected.role !== 'visitor'}
										<button class="action-chip" onclick={() => void startGuestDM(guest.id)}>DM</button>
									{/if}
								</div>
							{/each}
							{#if hasMoreMembers}
								<button class="load-more-members" onclick={() => void loadMembers(true)}>Load more</button>
							{/if}
							{#if selected.role === 'owner' && transferableMembers.length}
								<div class="transfer-section">
									<p class="rail-muted">Transfer ownership:</p>
									<form
										onsubmit={(e) => {
											e.preventDefault();
											const sel = (e.currentTarget as HTMLFormElement).querySelector('select');
											if (sel) void action(`/communities/${activeCommunityId()}/transfer`, 'POST', { user_id: sel.value });
										}}
									>
										<select required aria-label="New owner">
											<option value="" disabled selected>Choose a member</option>
											{#each transferableMembers as m (m.user_id)}<option value={m.user_id}>{m.display_name}</option>{/each}
										</select>
										<button class="btn-sm-primary" style="margin-top:8px">Transfer ownership</button>
									</form>
								</div>
							{/if}

						{:else}
							<!-- Settings panel -->
							<div class="settings-panel">
								<div class="settings-section">
									<div class="settings-section-head">Community details</div>
									{#if selected.role === 'owner'}
										<p class="save-status" role="status">{detailsStatus || 'Auto-saves'}</p>
										<label>Name<input required maxlength="100" bind:value={name} onblur={() => void saveDetails()} /></label>
										<label>Description<textarea maxlength="1000" bind:value={description} onblur={() => void saveDetails()}></textarea></label>
										<Autocomplete
											id="edit-school"
											label="School"
											bind:value={school}
											options={schools}
											popular={popularSchools}
											placeholder="Search US schools"
											help="Choose a school or type another name."
											onOpen={() => void loadSchools()}
										/>
										<Autocomplete
											id="edit-course"
											label="Course"
											bind:value={course}
											options={courseOptions}
											popular={courseOptions}
											placeholder="Search courses"
											help="Course codes vary by school."
										/>
									{/if}
								</div>
								<div class="settings-section">
									<div class="settings-section-head">Invite links</div>
									<p class="rail-muted">Invite classmates to this community.</p>
									<button class="btn-sm-primary" onclick={() => void createInvite()}>Create 7-day invite</button>
									{#if inviteLink}
										<input readonly aria-label="New invite link" value={inviteLink} onclick={(e) => e.currentTarget.select()} style="margin-top:8px" />
									{/if}
									{#each invites as invite (invite.id)}
										<div class="invite-row">
											<span>#{invite.id} · {invite.uses}{invite.max_uses ? `/${invite.max_uses}` : ''} uses{invite.revoked ? ' · Revoked' : ''}</span>
											{#if !invite.revoked}
												<button class="action-chip danger" onclick={() => void action(`/communities/${activeCommunityId()}/invites/${invite.id}`, 'DELETE')}>Revoke</button>
											{/if}
										</div>
									{/each}
									{#if selected.role === 'owner' || selected.role === 'moderator'}
										<div class="settings-share-row">
											<button class="btn-sm-outline" onclick={() => void shareChannel()}>Copy channel link</button>
										</div>
									{/if}
								</div>
								{#if selected.role === 'owner'}
									<div class="settings-section">
										<button class="btn-danger-outline" onclick={() => void deleteCommunity()}>Delete community</button>
									</div>
								{/if}
							</div>
						{/if}
					</aside>
				</div>

			{:else}
				<!-- Landing page -->
				<div class="landing">
					<div class="landing-hero">
						<p class="landing-eyebrow">StudySpot Communities</p>
						<h2>Find your people.<br />Make progress<br />together.</h2>
						<p class="landing-lead">
							Join a public study group, pick a channel, and start talking. Or create a space for
							the course you're working through.
						</p>
						<div class="landing-cta">
							<button class="btn-primary landing-cta-primary" onclick={showCreate}>Create a community</button>
							<button class="landing-cta-secondary" onclick={() => document.getElementById('community-search')?.focus()}>
								Browse communities
							</button>
						</div>
					</div>

					<div class="landing-features">
						<div class="feature-card">
							<span class="feature-icon" aria-hidden="true">#</span>
							<strong>Organized channels</strong>
							<p>Keep homework, exam prep, and casual chat in separate channels.</p>
						</div>
						<div class="feature-card">
							<span class="feature-icon" aria-hidden="true">✉</span>
							<strong>Direct messages</strong>
							<p>Message any member privately, outside of group channels.</p>
						</div>
						<div class="feature-card">
							<span class="feature-icon" aria-hidden="true">🔗</span>
							<strong>Invite links</strong>
							<p>Share a link to bring classmates into your public community.</p>
						</div>
					</div>

					<h3 class="explore-heading">Explore communities</h3>
					<div class="community-grid">
						{#each communities.slice(0, 6) as community (community.id)}
							<button class="community-card" onclick={() => void choose(community.id)}>
								<div class="community-card-icon" style="background:{avatarColor(community.name)}">
									{initials(community.name)}
								</div>
								<div class="community-card-info">
									<strong>{community.name}</strong>
									<span>{[community.school, community.course].filter(Boolean).join(' · ') || 'Open study community'}</span>
									<small>{community.member_count} {community.member_count === 1 ? 'member' : 'members'} · Public</small>
								</div>
							</button>
						{:else}
							<p class="muted">No communities yet. Start one for your class.</p>
						{/each}
					</div>
				</div>
			{/if}
		</div>
	</main>
{/if}
</div>

<style>
	/* ── Design tokens — OG StudySpot palette ── */
	:root {
		/* Sidebar (warm cream, matching OG site) */
		--sb-bg:       #f5f0ea;
		--sb-hover:    rgba(0,0,0,0.05);
		--sb-active:   rgba(155,28,58,0.10);
		--sb-border:   #e5ddd5;
		--sb-text:     #4a3f38;
		--sb-muted:    #9b8e84;
		--sb-text-act: #9b1c3a;

		/* Brand / actions */
		--accent:    #9b1c3a;
		--accent-h:  #7d1630;
		--accent-lt: #fdf2f5;

		/* Danger */
		--danger:    #c0392b;
	}

	/* ── Shell ── */
	.shell {
		min-height: 100vh;
		background: #fff;
	}

	.auth-loading {
		display: flex;
		align-items: center;
		justify-content: center;
		height: calc(100vh - 76px);
	}
	.auth-spinner {
		width: 32px;
		height: 32px;
		border: 3px solid #e5ddd5;
		border-top-color: #9b1c3a;
		border-radius: 50%;
		animation: spin 0.7s linear infinite;
	}
	@keyframes spin {
		to { transform: rotate(360deg); }
	}
	main {
		height: calc(100vh - 76px);
		min-height: 620px;
		display: grid;
		grid-template-columns: 248px minmax(0, 1fr);
	}

	/* ── Sidebar ── */
	.sidebar {
		background: var(--sb-bg);
		color: var(--sb-text);
		border-right: 1px solid var(--sb-border);
		display: flex;
		flex-direction: column;
		overflow: hidden;
		min-height: 0;
	}
	.sidebar-top {
		padding: 14px 10px 8px;
		flex-shrink: 0;
	}
	.home-link {
		display: block;
		width: 100%;
		text-align: left;
		border: 0;
		background: transparent;
		color: var(--sb-text-act);
		padding: 0 4px 10px;
		font: inherit;
		font-size: 15px;
		font-weight: 700;
		letter-spacing: -0.02em;
		cursor: pointer;
	}
	.sidebar-search-row {
		margin-bottom: 8px;
	}
	.sidebar-search-row input {
		width: 100%;
		background: #fff;
		border: 1px solid var(--sb-border);
		border-radius: 8px;
		color: var(--sb-text);
		padding: 7px 10px;
		font: inherit;
		font-size: 13px;
		box-sizing: border-box;
		transition: border-color 0.15s;
	}
	.sidebar-search-row input::placeholder { color: var(--sb-muted); }
	.sidebar-search-row input:focus {
		outline: none;
		border-color: var(--accent);
		box-shadow: 0 0 0 2px rgba(155,28,58,0.12);
	}
	.sidebar-tabs {
		display: flex;
		gap: 2px;
		background: rgba(0,0,0,0.06);
		border-radius: 8px;
		padding: 3px;
	}
	.sidebar-tabs button {
		flex: 1;
		padding: 5px 8px;
		min-height: 28px;
		border: 0;
		border-radius: 6px;
		background: transparent;
		color: var(--sb-muted);
		font: inherit;
		font-size: 12px;
		font-weight: 600;
		cursor: pointer;
		transition: background 0.12s, color 0.12s;
	}
	.sidebar-tabs button.chosen { color: var(--accent); background: #fff; }
	.sidebar-tabs button:hover:not(.chosen) { color: var(--sb-text); }

	.sidebar-section-label {
		font-size: 10px;
		text-transform: uppercase;
		letter-spacing: 0.09em;
		color: var(--sb-muted);
		font-weight: 700;
		padding: 12px 14px 4px;
		flex-shrink: 0;
	}
	.sidebar-list {
		display: flex;
		flex-direction: column;
		gap: 1px;
		overflow-y: auto;
		flex-shrink: 0;
		max-height: 260px;
		padding: 0 6px;
	}
	.sidebar-item {
		display: flex;
		align-items: center;
		gap: 10px;
		text-align: left;
		border: 0;
		border-radius: 8px;
		background: transparent;
		color: var(--sb-text);
		padding: 7px 8px;
		font: inherit;
		cursor: pointer;
		transition: background 0.1s, color 0.1s;
		border-left: 2px solid transparent;
	}
	.sidebar-item:hover { background: var(--sb-hover); }
	.sidebar-item.active {
		background: var(--sb-active);
		color: var(--sb-text-act);
	}
	.sidebar-item-icon {
		width: 28px;
		height: 28px;
		border-radius: 8px;
		display: grid;
		place-items: center;
		color: white;
		font-size: 11px;
		font-weight: 700;
		flex-shrink: 0;
		user-select: none;
	}
	.sidebar-item-avatar {
		width: 28px;
		height: 28px;
		border-radius: 50%;
		display: grid;
		place-items: center;
		color: white;
		font-size: 11px;
		font-weight: 700;
		flex-shrink: 0;
		user-select: none;
	}
	.sidebar-item-text {
		min-width: 0;
		display: flex;
		flex-direction: column;
		gap: 1px;
	}
	.sidebar-item-name {
		font-size: 13px;
		font-weight: 600;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		color: var(--sb-text);
	}
	.sidebar-item.active .sidebar-item-name { color: var(--sb-text-act); }
	.sidebar-item-meta {
		font-size: 11px;
		color: var(--sb-muted);
	}

	.sidebar-load-more {
		font-size: 12px;
		padding: 4px 14px;
		border: 0;
		background: transparent;
		color: var(--sb-muted);
		cursor: pointer;
		border-radius: 6px;
		font: inherit;
		flex-shrink: 0;
	}
	.sidebar-load-more:hover { color: var(--sb-text); }

	.sidebar-muted { font-size: 12px; color: var(--sb-muted); padding: 4px 14px; margin: 0; }

	.sidebar-bottom {
		margin-top: auto;
		padding: 10px 10px 14px;
		flex-shrink: 0;
	}
	.create-btn {
		display: block;
		width: 100%;
		padding: 9px 14px;
		border: 0;
		border-radius: 8px;
		background: var(--accent);
		color: white;
		font: inherit;
		font-size: 13px;
		font-weight: 700;
		cursor: pointer;
		transition: background 0.12s;
		text-align: center;
	}
	.create-btn:hover { background: var(--accent-h); }

	/* ── Content area ── */
	.content {
		display: flex;
		flex-direction: column;
		min-width: 0;
		min-height: 0;
		overflow-y: auto;
		background: #fff;
	}
	.content.workspace-mode {
		overflow: hidden;
	}

	.error-banner {
		padding: 10px 20px;
		background: var(--accent-lt);
		color: var(--accent);
		font-size: 13px;
		border-bottom: 1px solid rgba(155,28,58,0.15);
		flex-shrink: 0;
	}

	/* ── Workspace ── */
	.workspace {
		display: grid;
		grid-template-columns: 220px minmax(0, 1fr) 240px;
		flex: 1;
		height: 100%;
		min-height: 0;
		overflow: hidden;
	}

	/* Channel rail */
	.channel-rail {
		background: var(--sb-bg);
		border-right: 1px solid var(--sb-border);
		display: flex;
		flex-direction: column;
		overflow-y: auto;
		min-width: 0;
	}
	.community-header {
		display: flex;
		align-items: center;
		gap: 10px;
		padding: 14px 12px 12px;
		border-bottom: 1px solid var(--sb-border);
		flex-shrink: 0;
	}
	.community-avatar {
		width: 36px;
		height: 36px;
		border-radius: 10px;
		display: grid;
		place-items: center;
		color: white;
		font-size: 13px;
		font-weight: 700;
		flex-shrink: 0;
		user-select: none;
	}
	.community-header-text {
		min-width: 0;
		display: flex;
		flex-direction: column;
		gap: 2px;
	}
	.community-name {
		font-size: 13px;
		font-weight: 700;
		color: var(--sb-text-act);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		line-height: 1.2;
	}
	.community-meta {
		font-size: 11px;
		color: var(--sb-muted);
	}

	.rail-section {
		padding: 10px 6px 8px;
		flex: 1;
	}
	.rail-section-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 0 6px;
		margin-bottom: 4px;
		font-size: 10px;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.09em;
		color: var(--sb-muted);
	}
	.rail-add-btn {
		width: 20px;
		height: 20px;
		border: 0;
		background: transparent;
		color: var(--sb-muted);
		font-size: 18px;
		line-height: 1;
		cursor: pointer;
		border-radius: 4px;
		display: grid;
		place-items: center;
		padding: 0;
		transition: color 0.1s, background 0.1s;
	}
	.rail-add-btn:hover { color: var(--sb-text); background: var(--sb-hover); }
	.rail-add-btn:disabled { opacity: 0.4; cursor: default; }

	.channel-create-form {
		margin: 6px 4px 10px;
		padding: 10px;
		background: rgba(0,0,0,0.04);
		border-radius: 8px;
	}
	.channel-create-form input {
		width: 100%;
		background: #fff;
		border: 1px solid var(--sb-border);
		border-radius: 6px;
		padding: 6px 8px;
		font: inherit;
		font-size: 13px;
		color: #1a1a1a;
		box-sizing: border-box;
	}
	.channel-create-form input:focus { outline: none; border-color: var(--accent); box-shadow: 0 0 0 2px rgba(155,28,58,0.15); }
	.channel-name-hint {
		font-size: 11px;
		color: var(--sb-muted);
		margin: 4px 0 8px;
	}
	.mini-actions {
		display: flex;
		gap: 6px;
		flex-wrap: wrap;
	}
	.mini-actions button {
		font-size: 12px;
		padding: 4px 10px;
		border: 1px solid var(--sb-border);
		border-radius: 5px;
		background: #fff;
		color: var(--sb-text);
		cursor: pointer;
		font: inherit;
		font-size: 12px;
		font-weight: 600;
		transition: background 0.1s;
	}
	.mini-actions button:hover { background: var(--sb-hover); }
	.btn-sm-primary {
		background: var(--accent) !important;
		color: white !important;
	}
	.btn-sm-primary:hover:not([disabled]) { background: var(--accent-h) !important; }

	.channel-list {
		list-style: none;
		margin: 0;
		padding: 0;
		display: grid;
		gap: 1px;
	}
	.channel-item { position: relative; }
	.channel-row {
		display: flex;
		align-items: center;
		border-radius: 6px;
		transition: background 0.1s;
	}
	.channel-row:hover { background: var(--sb-hover); }
	.channel-row.active {
		background: var(--sb-active);
	}
	.channel-row.archived .ch-name { opacity: 0.5; }

	.channel-btn {
		flex: 1;
		display: flex;
		align-items: center;
		gap: 5px;
		min-width: 0;
		text-align: left;
		border: 0;
		background: transparent;
		color: var(--sb-muted);
		padding: 6px 8px;
		font: inherit;
		font-size: 13px;
		cursor: pointer;
		transition: color 0.1s;
		border-radius: 6px 0 0 6px;
	}
	.channel-row:hover .channel-btn { color: var(--sb-text); }
	.channel-row.active .channel-btn { color: var(--sb-text-act); font-weight: 600; }

	.ch-hash {
		color: var(--sb-muted);
		font-size: 16px;
		font-weight: 600;
		flex-shrink: 0;
	}
	.channel-row.active .ch-hash { color: var(--sb-text); }
	.ch-name {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.archived-chip {
		font-size: 9px;
		background: rgba(0,0,0,0.07);
		color: var(--sb-muted);
		border-radius: 3px;
		padding: 1px 4px;
		flex-shrink: 0;
	}
	.ch-options-btn {
		flex-shrink: 0;
		width: 28px;
		height: 28px;
		border: 0;
		background: transparent;
		color: var(--sb-muted);
		cursor: pointer;
		border-radius: 0 6px 6px 0;
		display: grid;
		place-items: center;
		font-size: 16px;
		opacity: 0;
		transition: opacity 0.1s, background 0.1s, color 0.1s;
		padding: 0;
	}
	.channel-row:hover .ch-options-btn { opacity: 1; }
	.ch-options-btn:hover { background: var(--sb-active); color: var(--sb-text-act); }

	.channel-menu {
		position: absolute;
		top: 36px;
		right: 0;
		z-index: 10;
		background: #fff;
		border: 1px solid var(--sb-border);
		border-radius: 10px;
		padding: 4px;
		min-width: 160px;
		box-shadow: 0 8px 24px rgba(0,0,0,0.12), 0 0 0 1px rgba(0,0,0,0.05);
		animation: fadeIn 0.1s ease;
	}
	.channel-menu button {
		display: block;
		width: 100%;
		text-align: left;
		border: 0;
		background: transparent;
		color: #1a1a1a;
		padding: 8px 10px;
		font: inherit;
		font-size: 13px;
		border-radius: 6px;
		cursor: pointer;
		transition: background 0.1s;
	}
	.channel-menu button:hover { background: var(--sb-hover); }
	.menu-danger { color: var(--danger) !important; }
	.menu-danger:hover { background: rgba(192,57,43,0.08) !important; }

	.rail-actions {
		padding: 8px 10px 14px;
		margin-top: auto;
		flex-shrink: 0;
	}
	.rail-join-btn, .rail-leave-btn {
		width: 100%;
		padding: 9px;
		border: 0;
		border-radius: 8px;
		font: inherit;
		font-size: 13px;
		font-weight: 600;
		cursor: pointer;
		transition: background 0.15s;
	}
	.rail-join-btn { background: var(--accent); color: white; border: none; }
	.rail-join-btn:hover { background: var(--accent-h); }
	.rail-leave-btn { background: rgba(0,0,0,0.05); color: var(--sb-text); border: none; }
	.rail-leave-btn:hover { background: rgba(0,0,0,0.09); color: #1a1a1a; }

	/* Chat area */
	.chat-area {
		display: flex;
		flex-direction: column;
		min-width: 0;
		min-height: 0;
		overflow: hidden;
		background: #fff;
	}
	.channel-pane {
		display: flex;
		flex-direction: column;
		flex: 1;
		min-height: 0;
	}
	.channel-edit-bar {
		padding: 10px 20px;
		background: #fffbf0;
		border-bottom: 1px solid #f0e0a0;
		flex-shrink: 0;
	}
	.channel-edit-bar form {
		display: flex;
		align-items: center;
		gap: 10px;
		flex-wrap: wrap;
	}
	.channel-edit-bar label {
		font-size: 13px;
		font-weight: 600;
		display: flex;
		align-items: center;
		gap: 4px;
		color: #1d1c1d;
	}
	.channel-edit-bar input {
		border: 1px solid #d8d8d8;
		border-radius: 4px;
		padding: 5px 8px;
		font: inherit;
		font-size: 13px;
		width: 160px;
	}
	.channel-edit-bar input:focus { outline: none; border-color: var(--accent); box-shadow: 0 0 0 2px rgba(155,28,58,0.15); }
	.save-hint { font-size: 11px; color: #6b6459; }
	.btn-danger-sm {
		color: var(--danger) !important;
		background: transparent !important;
	}

	.share-banner {
		padding: 8px 20px;
		background: #f0fff4;
		border-bottom: 1px solid #c3e6cb;
		flex-shrink: 0;
	}
	.share-msg { margin: 0 0 4px; font-size: 13px; color: #285736; }
	.share-link {
		width: 100%;
		border: 1px solid #a8d8bc;
		border-radius: 6px;
		padding: 6px 10px;
		font: inherit;
		font-size: 12px;
		background: white;
	}

	.join-wall {
		flex: 1;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		padding: 40px;
		text-align: center;
	}
	.join-wall-icon {
		width: 72px;
		height: 72px;
		border-radius: 18px;
		display: grid;
		place-items: center;
		font-size: 32px;
		font-weight: 700;
		color: white;
		margin-bottom: 20px;
	}
	.join-wall h3 { margin: 0 0 8px; font-size: 22px; color: #1d1c1d; }
	.join-wall p { color: #616061; margin: 0 0 20px; }

	.empty-channel {
		flex: 1;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		padding: 40px;
		text-align: center;
	}
	.empty-icon {
		font-size: 48px;
		color: #d4d2d8;
		margin-bottom: 16px;
	}
	.empty-channel h3 { margin: 0 0 8px; color: #1d1c1d; }
	.empty-channel p { color: #616061; margin: 0 0 20px; }

	/* Member rail */
	.member-rail {
		background: var(--sb-bg);
		border-left: 1px solid var(--sb-border);
		display: flex;
		flex-direction: column;
		overflow-y: auto;
		min-width: 0;
	}
	.member-rail-header {
		display: flex;
		gap: 2px;
		padding: 10px 8px 8px;
		border-bottom: 1px solid var(--sb-border);
		flex-shrink: 0;
	}
	.tab-link {
		flex: 1;
		font-size: 11px;
		font-weight: 600;
		padding: 6px 4px;
		border: 0;
		border-radius: 6px;
		background: transparent;
		color: var(--sb-muted);
		cursor: pointer;
		transition: background 0.1s, color 0.1s;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.tab-link:hover { background: var(--sb-hover); color: var(--sb-text); }
	.tab-link.chosen { background: var(--sb-active); color: var(--sb-text-act); }

	.rail-members-label {
		font-size: 10px;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.07em;
		color: var(--sb-muted);
		padding: 12px 12px 6px;
	}
	.rail-muted {
		font-size: 12px;
		color: var(--sb-muted);
		padding: 2px 12px 8px;
		margin: 0;
	}

	.member-card {
		display: flex;
		align-items: flex-start;
		gap: 8px;
		padding: 7px 10px;
		border-radius: 8px;
		margin: 0 4px;
		transition: background 0.1s;
		cursor: default;
	}
	.member-card:hover { background: var(--sb-hover); }
	.member-avatar {
		width: 36px;
		height: 36px;
		border-radius: 50%;
		display: grid;
		place-items: center;
		color: white;
		font-size: 12px;
		font-weight: 700;
		flex-shrink: 0;
		user-select: none;
	}
	.member-info {
		min-width: 0;
		flex: 1;
	}
	.member-info strong {
		display: block;
		font-size: 13px;
		color: var(--sb-text);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.member-info span {
		font-size: 11px;
		color: var(--sb-muted);
		text-transform: capitalize;
	}
	.dm-btn {
		border: 0;
		background: transparent;
		color: var(--sb-muted);
		cursor: pointer;
		font-size: 14px;
		padding: 3px 5px;
		border-radius: 4px;
		opacity: 0;
		transition: opacity 0.1s, background 0.1s;
		min-height: 0;
		flex-shrink: 0;
	}
	.member-card:hover .dm-btn { opacity: 1; }
	.dm-btn:hover { background: var(--sb-active); color: var(--sb-text-act); }

	.member-actions {
		display: flex;
		flex-wrap: wrap;
		gap: 4px;
		margin-top: 4px;
	}
	.action-chip {
		font-size: 11px;
		padding: 2px 8px;
		border: 1px solid var(--sb-border);
		border-radius: 100px;
		background: transparent;
		color: var(--sb-muted);
		cursor: pointer;
		transition: background 0.1s, color 0.1s;
		font: inherit;
		font-size: 11px;
		font-weight: 600;
	}
	.action-chip:hover { background: var(--sb-hover); color: var(--sb-text); }
	.action-chip.danger { color: var(--danger); border-color: rgba(192,57,43,0.3); }
	.action-chip.danger:hover { background: rgba(192,57,43,0.08); }

	.load-more-members {
		display: block;
		width: calc(100% - 24px);
		margin: 4px 12px;
		padding: 6px;
		border: 0;
		border-radius: 6px;
		background: rgba(0,0,0,0.04);
		color: var(--sb-muted);
		font: inherit;
		font-size: 12px;
		cursor: pointer;
		transition: background 0.1s;
	}
	.load-more-members:hover { background: var(--sb-hover); color: var(--sb-text); }

	.transfer-section {
		padding: 12px;
		border-top: 1px solid var(--sb-border);
		margin-top: 8px;
	}
	.transfer-section select {
		width: 100%;
		background: #fff;
		border: 1px solid var(--sb-border);
		color: var(--sb-text);
		border-radius: 6px;
		padding: 6px 8px;
		font: inherit;
		font-size: 13px;
	}

	/* Settings panel */
	.settings-panel {
		padding: 0 0 16px;
		overflow-y: auto;
	}
	.settings-section {
		padding: 12px 12px;
		border-bottom: 1px solid var(--sb-border);
	}
	.settings-section-head {
		font-size: 10px;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.07em;
		color: var(--sb-muted);
		margin-bottom: 10px;
	}
	.settings-section label {
		display: block;
		font-size: 11px;
		font-weight: 700;
		color: var(--sb-muted);
		text-transform: uppercase;
		letter-spacing: 0.05em;
		margin: 10px 0 4px;
	}
	.settings-section input,
	.settings-section textarea,
	.settings-section select {
		width: 100%;
		background: #fff;
		border: 1px solid var(--sb-border);
		color: #1a1a1a;
		border-radius: 6px;
		padding: 7px 8px;
		font: inherit;
		font-size: 13px;
		box-sizing: border-box;
	}
	.settings-section textarea { min-height: 80px; resize: vertical; }
	.settings-section input:focus,
	.settings-section textarea:focus,
	.settings-section select:focus {
		outline: none;
		border-color: var(--accent);
		box-shadow: 0 0 0 2px rgba(155,28,58,0.15);
	}
	.save-status {
		font-size: 11px;
		color: var(--sb-muted);
		margin: 0 0 4px;
	}
	.invite-row {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 8px;
		padding: 6px 0;
		font-size: 12px;
		color: var(--sb-muted);
		border-bottom: 1px solid var(--sb-border);
	}
	.settings-share-row {
		margin-top: 10px;
	}
	.btn-sm-outline {
		font-size: 12px;
		padding: 5px 10px;
		border: 1px solid var(--sb-border);
		border-radius: 6px;
		background: #fff;
		color: var(--sb-text);
		cursor: pointer;
		font: inherit;
		font-weight: 600;
		transition: background 0.1s;
	}
	.btn-sm-outline:hover { background: var(--sb-hover); }
	.btn-danger-outline {
		width: 100%;
		padding: 8px;
		border: 1px solid rgba(192,57,43,0.4);
		border-radius: 6px;
		background: transparent;
		color: var(--danger);
		font: inherit;
		font-size: 13px;
		font-weight: 600;
		cursor: pointer;
		transition: background 0.1s;
	}
	.btn-danger-outline:hover { background: rgba(192,57,43,0.08); }

	/* ── Create form page ── */
	.form-page {
		flex: 1;
		display: flex;
		align-items: flex-start;
		justify-content: center;
		padding: 48px 32px;
	}
	.form-page-inner {
		width: 100%;
		max-width: 520px;
	}
	.form-eyebrow {
		font-size: 11px;
		font-weight: 800;
		text-transform: uppercase;
		letter-spacing: 0.1em;
		color: var(--accent);
		margin: 0 0 12px;
	}
	.form-page-inner h2 { margin: 0 0 6px; font-size: 28px; font-weight: 800; letter-spacing: -0.03em; color: #1d1c1d; }
	.form-lead { color: #616061; margin: 0 0 28px; font-size: 15px; }
	.form-page-inner label {
		display: block;
		font-size: 13px;
		font-weight: 700;
		margin: 18px 0 6px;
		color: #1d1c1d;
	}
	.form-page-inner label span {
		display: block;
		font-size: 12px;
		font-weight: 700;
		color: #616061;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		margin-bottom: 6px;
	}
	.form-page-inner input,
	.form-page-inner textarea,
	.form-page-inner select {
		width: 100%;
		border: 1px solid #d8d8d8;
		border-radius: 4px;
		padding: 10px 12px;
		font: inherit;
		font-size: 14px;
		transition: border-color 0.15s, box-shadow 0.15s;
		box-sizing: border-box;
		color: #1d1c1d;
	}
	.form-page-inner textarea { min-height: 100px; resize: vertical; }
	.form-page-inner input:focus,
	.form-page-inner textarea:focus {
		outline: none;
		border-color: var(--accent);
		box-shadow: 0 0 0 2px rgba(155,28,58,0.15);
	}

	/* ── Shared buttons — Slack style ── */
	.form-actions {
		display: flex;
		flex-wrap: wrap;
		gap: 8px;
		margin-top: 24px;
	}
	.form-actions button {
		cursor: pointer;
		border: 1px solid #d8d8d8;
		border-radius: 4px;
		background: #fff;
		padding: 10px 22px;
		font: inherit;
		font-size: 14px;
		font-weight: 600;
		transition: background 0.1s, border-color 0.1s;
		color: #1d1c1d;
	}
	.form-actions button:hover { background: #f8f8f8; }
	.btn-primary {
		background: var(--accent) !important;
		color: white !important;
		border-color: var(--accent) !important;
	}
	.btn-primary:hover { background: var(--accent-h) !important; border-color: var(--accent-h) !important; }
	.btn-danger {
		background: var(--danger) !important;
		color: white !important;
		border-color: var(--danger) !important;
	}

	/* ── Dialog — Slack modal ── */
	.confirm-dialog {
		width: min(420px, calc(100vw - 32px));
		padding: 28px;
		border: 1px solid #e8e8e8;
		border-radius: 8px;
		box-shadow: 0 0 0 1px rgba(0,0,0,0.08), 0 20px 60px rgba(0,0,0,0.18);
	}
	.confirm-dialog::backdrop { background: rgba(0,0,0,0.5); }
	.confirm-dialog h2 { font-size: 22px; margin: 0 0 8px; color: #1d1c1d; }
	.confirm-dialog p { color: #616061; margin: 0 0 20px; }

	/* ── Landing page — Slack aesthetic ── */
	.landing {
		padding: 60px 56px 80px;
		max-width: 1000px;
	}
	.landing-eyebrow {
		font-size: 11px;
		font-weight: 800;
		text-transform: uppercase;
		letter-spacing: 0.1em;
		color: var(--accent);
		margin: 0 0 16px;
	}
	.landing h2 {
		font-size: clamp(38px, 5vw, 64px);
		line-height: 1.02;
		letter-spacing: -0.04em;
		margin: 0 0 20px;
		max-width: 680px;
		color: #1d1c1d;
		font-weight: 800;
	}
	.landing-lead {
		font-size: 17px;
		color: #616061;
		max-width: 560px;
		line-height: 1.65;
		margin: 0 0 32px;
	}
	.landing-cta {
		display: flex;
		flex-wrap: wrap;
		gap: 10px;
		margin-bottom: 56px;
	}
	.landing-cta-primary {
		padding: 13px 26px !important;
		font-size: 15px !important;
		font-weight: 700 !important;
		border-radius: 4px !important;
		cursor: pointer;
		border: 0 !important;
		background: var(--accent) !important;
		color: white !important;
		transition: background 0.15s, transform 0.1s !important;
	}
	.landing-cta-primary:hover { background: var(--accent-h) !important; transform: translateY(-1px); }
	.landing-cta-primary:active { transform: none; }
	.landing-cta-secondary {
		padding: 13px 26px;
		border: 1px solid #d8d8d8;
		border-radius: 4px;
		font: inherit;
		font-size: 15px;
		font-weight: 600;
		cursor: pointer;
		background: #fff;
		color: #1d1c1d;
		transition: background 0.15s, border-color 0.15s;
	}
	.landing-cta-secondary:hover { background: #f8f8f8; border-color: #aaa; }

	.landing-features {
		display: grid;
		grid-template-columns: repeat(3, 1fr);
		gap: 16px;
		margin-bottom: 56px;
	}
	.feature-card {
		padding: 22px;
		border: 1px solid #e8e8e8;
		border-radius: 4px;
		background: #f8f8f8;
		transition: box-shadow 0.15s;
	}
	.feature-card:hover {
		box-shadow: 0 0 0 1px rgba(0,0,0,0.1), 0 4px 12px rgba(0,0,0,0.06);
	}
	.feature-icon {
		display: block;
		font-size: 22px;
		margin-bottom: 12px;
		color: var(--accent);
	}
	.feature-card strong {
		display: block;
		font-size: 15px;
		margin-bottom: 6px;
		color: #1d1c1d;
	}
	.feature-card p {
		margin: 0;
		font-size: 13px;
		color: #616061;
		line-height: 1.55;
	}

	.explore-heading {
		font-size: 20px;
		font-weight: 700;
		margin: 0 0 16px;
		letter-spacing: -0.025em;
		color: #1d1c1d;
	}
	.community-grid {
		display: grid;
		grid-template-columns: repeat(2, 1fr);
		gap: 12px;
	}
	.community-card {
		display: flex;
		align-items: center;
		gap: 14px;
		text-align: left;
		padding: 18px;
		border: 1px solid #e8e8e8;
		border-radius: 4px;
		background: white;
		cursor: pointer;
		transition: border-color 0.15s, box-shadow 0.15s;
		font: inherit;
	}
	.community-card:hover {
		border-color: #aaa;
		box-shadow: 0 0 0 1px rgba(0,0,0,0.06), 0 4px 12px rgba(0,0,0,0.06);
	}
	.community-card-icon {
		width: 48px;
		height: 48px;
		border-radius: 8px;
		display: grid;
		place-items: center;
		color: white;
		font-size: 17px;
		font-weight: 700;
		flex-shrink: 0;
		user-select: none;
	}
	.community-card-info {
		min-width: 0;
		display: grid;
		gap: 3px;
	}
	.community-card-info strong { font-size: 14px; font-weight: 700; color: #1d1c1d; }
	.community-card-info span { font-size: 12px; color: #616061; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
	.community-card-info small { font-size: 11px; color: #aaa; }

	.muted { color: #616061; font-size: 13px; }

	/* ── Animations ── */
	@keyframes fadeIn {
		from { opacity: 0; transform: translateY(-4px); }
		to { opacity: 1; transform: translateY(0); }
	}

	/* ── Focus ── */
	button:focus-visible, input:focus-visible, textarea:focus-visible, select:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}
	button:disabled { opacity: 0.5; cursor: default; }

	/* ── Responsive ── */
	@media (max-width: 1200px) {
		.workspace { grid-template-columns: 200px minmax(0, 1fr) 210px; }
	}
	@media (max-width: 1050px) {
		.workspace { grid-template-columns: 180px minmax(0, 1fr) 190px; }
		.landing { padding: 40px 36px 60px; }
	}
	@media (max-width: 900px) {
		.workspace { grid-template-columns: 180px minmax(0, 1fr); }
		.member-rail { display: none; }
		.landing-features { grid-template-columns: 1fr; }
	}
	@media (max-width: 740px) {
		main { display: block; height: auto; }
		.workspace { display: block; }
		.channel-rail { border-right: 0; border-bottom: 1px solid var(--sb-border); }
		.landing { padding: 28px 22px 48px; }
		.community-grid { grid-template-columns: 1fr; }
		.landing-features { grid-template-columns: 1fr; }
	}
</style>
