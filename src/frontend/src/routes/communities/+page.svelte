<script lang="ts">
	import SiteHeader from '$lib/SiteHeader.svelte';
	import MoreHorizontal from '@lucide/svelte/icons/ellipsis';
	import SquarePen from '@lucide/svelte/icons/square-pen';
	import { chatControls } from '$lib/chatControls';
	import { Input } from '$lib/components/ui/input';
	import { Textarea } from '$lib/components/ui/textarea';
	import { NativeSelect } from '$lib/components/ui/native-select';
	import { base, resolve } from '$app/paths';
	import { onMount, tick } from 'svelte';
	import * as Card from '$lib/components/ui/card';
	import X from '@lucide/svelte/icons/x';
	import Moon from '@lucide/svelte/icons/moon';
	import Sun from '@lucide/svelte/icons/sun';
	import Compass from '@lucide/svelte/icons/compass';
	import Plus from '@lucide/svelte/icons/plus';
	import Hash from '@lucide/svelte/icons/hash';
	import MessageCircle from '@lucide/svelte/icons/message-circle';
	import Link2 from '@lucide/svelte/icons/link-2';
	import PanelLeft from '@lucide/svelte/icons/panel-left';
	import Users from '@lucide/svelte/icons/users';
	import '$lib/chat-theme.css';
	import Autocomplete from '$lib/Autocomplete.svelte';
	import { channelLink } from '$lib/chatLinks';
	import ChatInbox from '$lib/ChatInbox.svelte';
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

	type Person = {
		name: string;
		community: string;
		community_id: number;
		target: { user_id: string } | { guest_member_id: number };
	};
	let composing = $state(false);
	let recipientQuery = $state('');
	let preview = $state<{
		name: string;
		member_count: number;
		token: string;
		channel: number | null;
	} | null>(null);
	let accepting = $state(false);
	let inviteOpen = $state(false);
	let communityMenu = $state<HTMLDivElement>();
	let communityTrigger: HTMLElement | null = null;
	let menuCommunity = $state<Community | null>(null);
	let menuLeft = $state(0),
		menuTop = $state(0);
	let headerHeight = $state(76);
	let people = $state<Person[]>([]);
	let peopleStatus = $state('');
	$effect(() => {
		const term = (composing ? recipientQuery : query).trim();
		people = [];
		peopleStatus = '';
		if (
			term.length < 2 ||
			(!composing && (selected || selectedDM)) ||
			(!guestPreview && session.status !== 'signed-in')
		)
			return;
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
				if (current) peopleStatus = message(cause);
			}
		}, 180);
		return () => {
			current = false;
			clearTimeout(timer);
		};
	});
	async function messagePerson(person: Person) {
		try {
			const chat = await communityRequest<DirectConversation>(
				`/communities/${person.community_id}/dms`,
				'POST',
				person.target
			);
			query = '';
			composing = false;
			openDM(chat);
		} catch (cause) {
			peopleStatus = message(cause);
		}
	}
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
	let selfName = $derived([...members, ...guestMembers].find((m) => m.is_me)?.display_name);
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
	let theme = $state<'light' | 'dark'>('light');
	let channelsOpen = $state(false);
	let joining = $state<number | null>(null);
	let navOpen = $state(false),
		membersOpen = $state(false);
	function toggleTheme() {
		theme = theme === 'light' ? 'dark' : 'light';
		localStorage.setItem('studyspot.chat.theme', theme);
	}
	let guestPreview = $state(false);
	let accessError = $state('');
	let inviteLink = $state('');
	let inviteCopyStatus = $state('');
	let shareLink = $state('');
	let copyStatus = $state('');
	let tab = $state<'main' | 'members' | 'settings'>('main');
	let requestNumber = 0;
	const activeCommunityId = () => selected?.id;

	const palette = ['#5865b9', '#976689', '#377f73', '#95634d', '#79659b', '#43728b', '#8c6441'];
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

	async function enterFromExplore(community: Community) {
		if (joining !== null) return;
		joining = community.id;
		try {
			if (community.role === 'visitor') {
				await communityRequest('/communities/' + community.id + '/join', 'POST');
			}
			await choose(community.id);
			if (selected?.id === community.id) {
				await tick();
				document.querySelector<HTMLElement>('.content')?.focus();
				await browse();
			}
		} catch (cause) {
			error = message(cause);
		} finally {
			joining = null;
		}
	}

	async function choose(id: number, channelId?: number | null) {
		navOpen = false;
		channelsOpen = false;
		membersOpen = false;
		const initial = new URL(location.href);
		const hash =
			Number(initial.searchParams.get('id')) === id &&
			Number(initial.searchParams.get('channel')) === channelId
				? initial.hash
				: '';
		error = '';
		try {
			selected = await communityRequest<Community>(`/communities/${id}`);
			selectedDM = null;
			channelCreateOpen = false;
			channelMenuOpen = null;
			editingChannelId = null;
			shareLink = '';
			inviteLink = '';
			inviteCopyStatus = '';
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
				`?id=${id}${activeChannelId ? `&channel=${activeChannelId}` : ''}${hash}`
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
		navOpen = false;
		channelsOpen = false;
		selectedDM = conversation;
		selected = null;
		creating = false;
		history.replaceState(
			null,
			'',
			`?dm=${conversation.id}${Number(new URL(location.href).searchParams.get('dm')) === conversation.id ? location.hash : ''}`
		);
		void loadDMs();
	}

	function goHome() {
		navOpen = false;
		channelsOpen = false;
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
		navOpen = false;
		channelsOpen = false;
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
		if (communityMenu?.matches(':popover-open')) {
			communityMenu.hidePopover();
			communityTrigger?.focus();
			return;
		}
		if (
			(navOpen || channelsOpen) &&
			channelMenuOpen === null &&
			!channelCreateOpen &&
			editingChannelId === null
		) {
			document
				.querySelector<HTMLButtonElement>(
					channelsOpen
						? '[aria-controls="channel-navigation"]'
						: '[aria-controls="community-navigation"]'
				)
				?.focus();
			navOpen = false;
			channelsOpen = false;
			return;
		}
		if (channelMenuOpen !== null) {
			const channelId = channelMenuOpen;
			channelMenuOpen = null;
			void tick().then(() => document.getElementById(`channel-trigger-${channelId}`)?.focus());
		} else if (editingChannelId !== null) void cancelChannelRename(editingChannelId);
		else if (channelCreateOpen) void closeChannelCreate();
	}

	async function shareChannel() {
		if (!selected || !activeChannelId) return;
		shareLink = channelLink(location.origin + resolve('/communities'), {
			community: selected.id,
			channel: activeChannelId
		});
		try {
			await navigator.clipboard.writeText(shareLink);
			copyStatus = 'Channel link copied.';
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

	function openCommunityMenu(event: MouseEvent, community: Community) {
		event.preventDefault();
		communityTrigger = event.currentTarget as HTMLElement;
		const rect = communityTrigger.getBoundingClientRect();
		const pointer = event.type === 'contextmenu' && (event.clientX || event.clientY);
		menuLeft = Math.max(4, Math.min(pointer ? event.clientX : rect.left, innerWidth - 232));
		menuTop = Math.max(4, Math.min(pointer ? event.clientY : rect.bottom, innerHeight - 275));
		menuCommunity = community;
		communityMenu?.showPopover();
		void tick().then(() => communityMenu?.querySelector('button')?.focus());
	}

	async function communityOption(option: 'open' | 'settings' | 'create' | 'leave' | 'invite') {
		const target = menuCommunity;
		communityMenu?.hidePopover();
		if (!target) return;
		if (option === 'leave') {
			if (!confirm('Leave ' + target.name + '?')) return;
			try {
				await communityRequest('/communities/' + target.id + '/leave', 'POST');
				if (selected?.id === target.id) goHome();
				await browse();
			} catch (cause) {
				error = message(cause);
			}
			return;
		}
		if (selected?.id !== target.id) await choose(target.id);
		if (selected?.id !== target.id) return;
		if (option === 'invite') {
			inviteLink = '';
			inviteOpen = true;
			await createInvite();
		}
		if (option === 'settings') {
			membersOpen = true;
			await loadSettings();
		}
		if (option === 'create') {
			navOpen = false;
			channelsOpen = true;
			await openChannelCreate();
		}
	}

	async function acceptInvite() {
		if (!preview || accepting) return;
		accepting = true;
		try {
			const result = await communityRequest<{ community_id: number }>(
				'/communities/invites/' + encodeURIComponent(preview.token) + '/redeem',
				'POST'
			);
			await choose(result.community_id, preview.channel);
			preview = null;
			await browse();
		} catch (cause) {
			error = message(cause);
		} finally {
			accepting = false;
		}
	}

	async function createInvite() {
		if (!selected) return;
		inviteCopyStatus = '';
		try {
			const result = await communityRequest<{ token: string }>(
				`/communities/${selected.id}/invites`,
				'POST',
				{ expires_in_hours: 168, max_uses: 100 }
			);
			inviteLink = channelLink(location.origin + resolve('/communities'), {
				invite: result.token,
				channel: activeChannelId
			});
			if (!inviteOpen) await loadSettings();
		} catch (cause) {
			error = message(cause);
		}
	}

	$effect(() => {
		if (!guestPreview && session.status !== 'signed-in') return;
		void browse(query, false, viewMine);
	});

	onMount(() => {
		const saved = localStorage.getItem('studyspot.chat.theme');
		theme =
			saved === 'light' || saved === 'dark'
				? saved
				: matchMedia('(prefers-color-scheme: dark)').matches
					? 'dark'
					: 'light';
		const url = new URL(location.href);
		async function enter() {
			const access = await communityRequest<{ guest_preview: boolean }>('/communities/access');
			guestPreview = access.guest_preview;
			if (!guestPreview) await session.start();
			if (!guestPreview && session.status === 'signed-out') {
				session.logIn(location.pathname + location.search + location.hash);
				return;
			}
			if (!guestPreview && session.status !== 'signed-in') return;
			const token = url.searchParams.get('invite');
			const channelId = Number(url.searchParams.get('channel')) || null;
			const id = Number(url.searchParams.get('id'));
			const dmId = Number(url.searchParams.get('dm'));
			try {
				if (token) {
					const details = await communityRequest<{ name: string; member_count: number }>(
						'/communities/invites/' + encodeURIComponent(token)
					);
					preview = { ...details, token, channel: channelId };
				} else if (dmId) {
					openDM(await communityRequest<DirectConversation>(`/dms/${dmId}`));
					return;
				} else if (id) {
					await choose(id, channelId);
				}
				await loadDMs();
			} catch (e) {
				error = message(e);
			}
		}
		void enter().catch((e) => (accessError = message(e)));
		const refreshDMs = () => {
			if (!document.hidden && (guestPreview || session.status === 'signed-in')) void loadDMs();
		};
		document.addEventListener('visibilitychange', refreshDMs);
		const refreshTimer = window.setInterval(refreshDMs, 8000);
		return () => {
			clearInterval(refreshTimer);
			document.removeEventListener('visibilitychange', refreshDMs);
		};
	});
</script>

<svelte:window
	onkeydown={handleEscape}
	onpointerdown={(event) => {
		if (
			communityMenu?.matches(':popover-open') &&
			event.target instanceof Node &&
			!communityMenu.contains(event.target)
		)
			communityMenu.hidePopover();
	}}
/>

<svelte:head>
	<title>Communities · StudySpot</title>
	<meta name="description" content="Find and create public study communities." />
</svelte:head>

<div class="site-navigation" data-theme={theme} bind:clientHeight={headerHeight}>
	<SiteHeader />
</div>
<div class="shell chat-shell" data-theme={theme} style:--site-header-height={headerHeight + 'px'}>
	{#if accessError}<p role="alert">
			{accessError}
		</p>{:else if !guestPreview && session.status === 'loading'}
		<div class="auth-loading" aria-label="Loading…">
			<span class="auth-spinner" aria-hidden="true"></span>
		</div>
	{:else if !guestPreview && (session.status === 'signed-out' || session.status === 'disabled' || session.status === 'error')}
		<p role="status">
			{session.status === 'signed-out'
				? 'Opening sign-in…'
				: 'Sign-in is unavailable. Please check your account configuration.'}
		</p>
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
					<button class={chatControls.ghost} onclick={() => deleteDialog?.close()}>Cancel</button>
					<button class="btn-danger {chatControls.danger}" onclick={() => void deleteChannel()}
						>Delete channel</button
					>
				</div>
			{/if}
		</dialog>

		<div
			bind:this={communityMenu}
			popover="manual"
			class="community-pop"
			style:left={menuLeft + 'px'}
			style:top={menuTop + 'px'}
			role="group"
			aria-label="Community actions"
		>
			{#if menuCommunity}<strong>{menuCommunity.name}</strong>
				<button onclick={() => void communityOption('open')}>Open community</button>
				{#if menuCommunity.role === 'owner' || menuCommunity.role === 'moderator'}
					<button onclick={() => void communityOption('settings')}>Community settings</button>
					<button onclick={() => void communityOption('invite')}>Invite people</button>
				{/if}
				{#if menuCommunity.role === 'owner'}<button onclick={() => void communityOption('create')}
						>Create channel</button
					>{/if}
				{#if menuCommunity.role === 'member' || menuCommunity.role === 'moderator'}<button
						onclick={() => void communityOption('leave')}>Leave community…</button
					>{/if}
			{/if}
		</div>
		{#if composing}
			<dialog
				class="confirm-dialog flow-dialog"
				aria-labelledby="compose-title"
				{@attach (node) => node.showModal()}
				onclose={() => (composing = false)}
			>
				<h2 id="compose-title">New message</h2>
				<label for="recipient-search">Find someone in your communities</label>
				<Input
					id="recipient-search"
					bind:value={recipientQuery}
					maxlength={100}
					placeholder="Type at least two letters"
				/>
				<p role="status">{peopleStatus}</p>
				{#each people as person (person.community_id + JSON.stringify(person.target))}
					<button class={chatControls.row} onclick={() => void messagePerson(person)}
						>{person.name} · {person.community}</button
					>{/each}
				<button class={chatControls.ghost} onclick={() => (composing = false)}>Cancel</button>
			</dialog>{/if}
		{#snippet generatedInvite()}{#if inviteLink}
				<Input
					readonly
					aria-label="New invite link"
					value={inviteLink}
					onclick={(e) => e.currentTarget.select()}
					style="margin-top:8px"
				/>
				<button
					class={chatControls.ghost}
					onclick={async () => {
						try {
							await navigator.clipboard.writeText(inviteLink);
							inviteCopyStatus = 'Invite link copied.';
						} catch {
							inviteCopyStatus = 'Select the link above and copy it.';
						}
					}}>Copy invite link</button
				>
				<small role="status">{inviteCopyStatus}</small>
			{/if}{/snippet}
		{#if inviteOpen}
			<dialog
				class="confirm-dialog flow-dialog"
				aria-labelledby="share-title"
				{@attach (node) => node.showModal()}
				onclose={() => (inviteOpen = false)}
			>
				<h2 id="share-title">Invite people</h2>
				<p>
					Invite a classmate to {selected?.name}. This link opens the selected channel and expires
					in seven days.
				</p>
				{#if error}<p role="alert">{error}</p>{:else if !inviteLink}<p role="status">
						Creating invitation…
					</p>{/if}
				{@render generatedInvite()}
				<button class={chatControls.ghost} onclick={() => (inviteOpen = false)}>Done</button>
			</dialog>{/if}

		{#if preview}
			<dialog
				class="confirm-dialog flow-dialog"
				aria-labelledby="invite-title"
				{@attach (node) => node.showModal()}
				onclose={() => {
					preview = null;
					goHome();
				}}
			>
				<small>COMMUNITY INVITATION</small>
				<h2 id="invite-title">{preview.name}</h2>
				<p>
					{preview.member_count}
					{preview.member_count === 1 ? 'member' : 'members'} · Accept to join and open the shared channel.
				</p>
				{#if error}<p role="alert">{error}</p>{/if}
				<button
					class="btn-primary {chatControls.primary}"
					disabled={accepting}
					onclick={() => void acceptInvite()}>{accepting ? 'Joining…' : 'Accept invite'}</button
				>
				<button
					class={chatControls.ghost}
					disabled={accepting}
					onclick={() => {
						preview = null;
						goHome();
					}}>Decline</button
				>
			</dialog>{/if}
		<main
			class:in-room={!!selected || !!selectedDM}
			class:nav-open={navOpen}
			class:channels-open={channelsOpen}
			class:members-open={membersOpen}
		>
			<!-- ── Left sidebar ── -->
			<aside id="community-navigation" class="sidebar" aria-label="Communities and direct messages">
				<div class="sidebar-top">
					<button
						class="home-link {chatControls.row}"
						onclick={goHome}
						title="Browse communities"
						aria-label="Browse communities"><Compass size={23} /><span>Communities</span></button
					>
					<div class="sidebar-search-row">
						<Input
							id="community-search"
							bind:value={query}
							maxlength={100}
							aria-label="Search people and communities"
							placeholder="Search people or communities…"
						/>
					</div>
					<div class="sidebar-tabs">
						<button
							class={chatControls.ghost}
							aria-pressed={!viewMine}
							class:chosen={!viewMine}
							onclick={() => (viewMine = false)}>All</button
						><button
							class={chatControls.ghost}
							aria-pressed={viewMine}
							class:chosen={viewMine}
							onclick={() => (viewMine = true)}>Mine</button
						>
					</div>
				</div>

				<div class="sidebar-scroll">
					{#if loading}<p class="sidebar-muted">Loading…</p>{/if}

					{#if query.trim().length >= 2 && !selected && !selectedDM}
						<div class="sidebar-section-label">People in your communities</div>
						{#if peopleStatus}<p role="status" class="sidebar-muted">{peopleStatus}</p>{/if}
						<div class="sidebar-list">
							{#each people as person (person.community_id + JSON.stringify(person.target))}
								<button
									class="sidebar-item {chatControls.row}"
									aria-label={'Message ' + person.name}
									onclick={() => void messagePerson(person)}
								>
									<span class="sidebar-item-avatar" style="background:{avatarColor(person.name)}"
										>{initials(person.name)}</span
									>
									<span class="sidebar-item-text"
										><strong class="sidebar-item-name">{person.name}</strong><small
											class="sidebar-item-meta">{person.community}</small
										></span
									>
								</button>{/each}
						</div>{/if}
					<div class="sidebar-section-label">Communities</div>
					<div class="sidebar-list">
						{#each communities as community (community.id)}
							<button
								class="sidebar-item {chatControls.row}"
								title={community.name}
								oncontextmenu={(event) => openCommunityMenu(event, community)}
								aria-label={community.name}
								class:active={selected?.id === community.id}
								aria-current={selected?.id === community.id ? 'page' : undefined}
								onclick={() => void choose(community.id)}
							>
								<div class="sidebar-item-icon" style="background:{avatarColor(community.name)}">
									{initials(community.name)}
								</div>
								<div class="sidebar-item-text">
									<span class="sidebar-item-name">{community.name}</span>
									<span class="sidebar-item-meta"
										>{community.member_count}
										{community.member_count === 1 ? 'member' : 'members'}</span
									>
								</div>
							</button>
						{/each}
					</div>
					{#if hasMore}
						<button
							class="sidebar-load-more {chatControls.ghost}"
							onclick={() => void browse(query, true)}>Show more</button
						>
					{/if}

					{#if directConversations.length}
						<div class="sidebar-section-label">Direct Messages</div>
						<div class="sidebar-list">
							{#each directConversations as conversation (conversation.id)}
								<button
									class="sidebar-item {chatControls.row}"
									title={conversation.other_name}
									aria-label={conversation.other_name}
									class:active={selectedDM?.id === conversation.id}
									aria-current={selectedDM?.id === conversation.id ? 'page' : undefined}
									onclick={() => openDM(conversation)}
								>
									<div
										class="sidebar-item-avatar"
										style="background:{avatarColor(conversation.other_name)}"
									>
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
				</div>
				<div class="sidebar-bottom">
					<button
						class="create-btn {chatControls.primary}"
						title="Create community"
						aria-label="Create community"
						onclick={showCreate}><Plus size={21} /><span>New community</span></button
					>
				</div>
			</aside>

			<!-- ── Main content ── -->
			<div class="content" tabindex="-1" class:workspace-mode={!!selected || !!selectedDM}>
				<header class="room-bar">
					<button
						class="chat-icon mobile-nav {chatControls.icon}"
						aria-label="Toggle navigation"
						title="Communities and direct messages"
						aria-controls="community-navigation"
						aria-expanded={navOpen}
						onclick={async () => {
							channelsOpen = false;
							membersOpen = false;
							navOpen = !navOpen;
							await tick();
							if (navOpen) document.getElementById('community-search')?.focus();
						}}><PanelLeft size={18} /></button
					>
					{#if selected}<button
							class="chat-icon mobile-nav {chatControls.icon}"
							title="Channels"
							aria-label="Toggle channels"
							aria-controls="channel-navigation"
							aria-expanded={channelsOpen}
							onclick={async () => {
								navOpen = false;
								membersOpen = false;
								channelsOpen = !channelsOpen;
								await tick();
								if (channelsOpen)
									document.querySelector<HTMLElement>('#channel-navigation button')?.focus();
							}}><Hash size={18} /></button
						>{/if}
					<button
						class={chatControls.ghost}
						onclick={() => {
							recipientQuery = '';
							composing = true;
						}}><SquarePen size={16} /> New message</button
					>
					<div class="app-controls">
						{#if selected}<button
								class="chat-icon members-toggle {chatControls.icon}"
								title="Toggle member list"
								aria-label="Toggle member list"
								aria-expanded={membersOpen}
								onclick={() => {
									channelsOpen = false;
									navOpen = false;
									membersOpen = !membersOpen;
								}}><Users size={18} /></button
							>{/if}<ChatInbox /><button
							class="chat-icon {chatControls.icon}"
							aria-label={'Switch to ' + (theme === 'light' ? 'dark' : 'light') + ' theme'}
							title="Switch theme"
							onclick={toggleTheme}
							>{#if theme === 'light'}<Moon size={18} />{:else}<Sun size={18} />{/if}</button
						>
					</div>
				</header>
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
									<Input
										required
										maxlength={100}
										bind:value={name}
										placeholder="Math 51A Study Group"
									/>
								</label>
								<label>
									<span>Description</span>
									<Textarea maxlength={1000} bind:value={description}></Textarea>
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
									<button class="btn-primary {chatControls.primary}">Create community</button>
									<button class={chatControls.ghost} type="button" onclick={goHome}>Cancel</button>
								</div>
							</form>
						</div>
					</div>
				{:else if selectedDM}
					{#key selectedDM.id}<DirectMessages conversation={selectedDM} />{/key}
				{:else if selected}
					<!-- Community workspace -->
					<div class="workspace">
						<!-- Channel rail (left) -->
						<nav
							id="channel-navigation"
							class="channel-rail"
							aria-label={`Channels in ${selected.name}`}
						>
							<div class="community-header">
								<div
									class="community-avatar"
									style="background:{avatarColor(selected.name)}"
									aria-hidden="true"
								>
									{initials(selected.name)}
								</div>
								<div class="community-header-text">
									<span class="community-name">{selected.name}</span>
									<span class="community-meta"
										>{selected.member_count}
										{selected.member_count === 1 ? 'member' : 'members'}</span
									>
								</div>
								<button
									class={chatControls.icon}
									aria-label="Community actions"
									title="Community actions"
									onclick={(event) => selected && openCommunityMenu(event, selected)}
									><MoreHorizontal size={18} /></button
								>
							</div>

							<div class="rail-section">
								<div class="rail-section-header">
									<span>Text channels</span>
									{#if selected.role === 'owner'}
										<button
											class="rail-add-btn {chatControls.icon}"
											id="add-channel-button"
											aria-label="Add channel"
											title={(selected.channels?.length ?? 0) >= 20
												? 'Channel limit reached'
												: 'Add channel'}
											disabled={(selected.channels?.length ?? 0) >= 20}
											onclick={() => void openChannelCreate()}>+</button
										>
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
										<Input
											id="new-channel-name"
											bind:ref={channelNameInput}
											required
											pattern="[a-z0-9][a-z0-9-]*"
											maxlength={50}
											bind:value={channelName}
											placeholder="channel-name"
										/>
										<p class="channel-name-hint">Lowercase, numbers, hyphens only.</p>
										<div class="mini-actions">
											<button class="btn-sm-primary {chatControls.primary}">Create</button>
											<button
												class={chatControls.ghost}
												type="button"
												onclick={() => void closeChannelCreate()}>Cancel</button
											>
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
													class="channel-btn {chatControls.row}"
													id={`channel-select-${channel.id}`}
													oncontextmenu={(e) => {
														e.preventDefault();
														void toggleChannelMenu(channel.id);
													}}
													aria-current={activeChannelId === channel.id ? 'page' : undefined}
													onclick={() => selectChannel(channel.id)}
												>
													<Hash size={18} />
													<span class="ch-name">{channel.name}</span>
													{#if channel.archived}<span class="archived-chip">archived</span>{/if}
												</button>
												<button
													class="ch-options-btn {chatControls.icon}"
													id={`channel-trigger-${channel.id}`}
													aria-label={`Options for #${channel.name}`}
													aria-expanded={channelMenuOpen === channel.id}
													aria-controls={`channel-options-${channel.id}`}
													onclick={() => void toggleChannelMenu(channel.id)}>⋯</button
												>
											</div>
											{#if channelMenuOpen === channel.id}
												<div
													class="channel-menu"
													id={`channel-options-${channel.id}`}
													role="group"
													aria-label={`Options for #${channel.name}`}
												>
													<button
														class={chatControls.ghost}
														onclick={() => {
															selectChannel(channel.id);
															void shareChannel();
														}}>Copy channel link</button
													>
													{#if selected.role === 'owner'}<button
															class={chatControls.ghost}
															onclick={() => void startChannelRename(channel)}
															>Channel settings</button
														>
														<button
															class={chatControls.ghost}
															disabled={channel.position === 0}
															onclick={() =>
																void updateChannel(channel.id, { position: channel.position - 1 })}
															>↑ Move up</button
														>
														<button
															class={chatControls.ghost}
															disabled={channel.position >= (selected.channels?.length ?? 0) - 1}
															onclick={() =>
																void updateChannel(channel.id, { position: channel.position + 1 })}
															>↓ Move down</button
														>
														<button
															class={chatControls.ghost}
															onclick={() =>
																void updateChannel(channel.id, { archived: !channel.archived })}
														>
															{channel.archived ? 'Restore channel' : 'Archive channel'}
														</button>
														<button
															class="menu-danger {chatControls.danger}"
															onclick={() => void confirmChannelDelete(channel)}
															>Delete channel</button
														>{/if}
												</div>
											{/if}
										</li>
									{/each}
								</ul>
							</div>

							<!-- Community action buttons at bottom of rail -->
							<div class="rail-actions">
								{#if selfName}<div class="self-card">
										<span style:background={avatarColor(selfName)}>{initials(selfName)}</span>
										<div>
											<strong>{selfName}</strong><small
												>{guestPreview ? 'Demo session' : 'Your profile'}</small
											>
										</div>
									</div>{/if}
								{#if selected.role === 'visitor'}
									<button
										class="rail-join-btn {chatControls.primary}"
										onclick={() => void action(`/communities/${activeCommunityId()}/join`)}
									>
										Join community
									</button>
								{:else if selected.role !== 'owner'}
									<button
										class="rail-leave-btn {chatControls.ghost}"
										onclick={() => {
											menuCommunity = selected;
											void communityOption('leave');
										}}
									>
										Leave community
									</button>
								{/if}
							</div>
						</nav>

						<!-- Chat area (center) -->
						<div class="chat-area">
							{#each selected.channels?.filter((ch) => ch.id === activeChannelId) ?? [] as channel (channel.id)}
								<div class="channel-pane">
									{#if selected.role === 'visitor'}<div class="visitor-channel">
											<Hash size={20} /><strong>{channel.name}</strong><button
												class="chat-icon {chatControls.icon}"
												title="Copy channel link"
												aria-label="Copy channel link"
												onclick={() => void shareChannel()}><Link2 size={18} /></button
											>
										</div>{/if}
									{#if editingChannelId === channel.id}
										<div class="channel-edit-bar">
											<h3>Channel settings</h3>
											<form
												onsubmit={(e) => {
													e.preventDefault();
													void finishChannelEdit(channel.id);
												}}
											>
												<label
													>Topic <Input
														maxlength={256}
														value={channel.topic ?? ''}
														onchange={(e) =>
															void updateChannel(channel.id, { topic: e.currentTarget.value })}
													/></label
												>
												<label
													><input
														type="checkbox"
														checked={channel.private}
														onchange={(e) =>
															void updateChannel(channel.id, { private: e.currentTarget.checked })}
													/> Private to moderators and owner</label
												>
												<label
													><input
														type="checkbox"
														checked={channel.read_only}
														onchange={(e) =>
															void updateChannel(channel.id, {
																read_only: e.currentTarget.checked
															})}
													/> Only moderators and owner can post</label
												>
												<label
													>Slowmode (seconds)<Input
														type="number"
														min="0"
														max="21600"
														value={channel.slowmode_seconds ?? 0}
														onchange={(e) =>
															void updateChannel(channel.id, {
																slowmode_seconds: e.currentTarget.valueAsNumber
															})}
													/></label
												>
												<label for={`rename-channel-${channel.id}`}>Rename #</label>
												<Input
													id={`rename-channel-${channel.id}`}
													bind:ref={renameInput}
													required
													pattern="[a-z0-9][a-z0-9-]*"
													maxlength={50}
													bind:value={renameValue}
													aria-describedby={`rename-status-${channel.id}`}
												/>
												<span id={`rename-status-${channel.id}`} class="save-hint" role="status">
													{channelStatus || 'Saves automatically'}
												</span>
												<div class="mini-actions">
													<button
														class="btn-sm-primary {chatControls.primary}"
														disabled={channelSaving}>Done</button
													>
													<button
														class={chatControls.ghost}
														type="button"
														onclick={() => void cancelChannelRename(channel.id)}>Close</button
													>
													<button
														class={chatControls.ghost}
														type="button"
														onclick={() =>
															void updateChannel(channel.id, { archived: !channel.archived })}
													>
														{channel.archived ? 'Restore' : 'Archive'}
													</button>
													<button
														type="button"
														class="btn-danger-sm {chatControls.danger}"
														onclick={() => void confirmChannelDelete(channel)}>Delete</button
													>
												</div>
											</form>
										</div>
									{/if}

									{#if copyStatus || shareLink}
										<div class="share-banner">
											{#if copyStatus}<p class="share-msg">{copyStatus}</p>{/if}
											{#if shareLink}
												<Input
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
											<div
												class="join-wall-icon"
												aria-hidden="true"
												style="background:{avatarColor(channel.name)}"
											>
												#
											</div>
											<h3>Join to participate</h3>
											<p>Join this community to read and send messages in #{channel.name}.</p>
											<button
												class="btn-primary {chatControls.primary}"
												onclick={() => void action(`/communities/${activeCommunityId()}/join`)}
											>
												Join community
											</button>
										</div>
									{:else}
										<ChannelChat
											communityId={selected.id}
											{channel}
											role={selected.role}
											names={[...members, ...guestMembers].map((m) => m.display_name)}
											onShare={() => void shareChannel()}
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
										<button
											class="btn-primary {chatControls.primary}"
											onclick={() => void openChannelCreate()}>Add channel</button
										>
									{/if}
								</div>
							{/each}
						</div>

						<!-- Members rail (right) -->
						<aside class="member-rail" aria-label={`Members of ${selected.name}`}>
							<!-- Tab header -->
							<div class="member-rail-header">
								<button
									class="tab-link {chatControls.ghost}"
									class:chosen={tab === 'main'}
									onclick={() => (tab = 'main')}>Overview</button
								>
								<button
									class="tab-link {chatControls.ghost}"
									class:chosen={tab === 'members'}
									onclick={() => {
										tab = 'members';
										void loadMembers();
									}}>Members</button
								>
								{#if selected.role === 'owner' || selected.role === 'moderator'}
									<button
										class="tab-link {chatControls.ghost}"
										class:chosen={tab === 'settings'}
										onclick={() => void loadSettings()}>Manage</button
									>
								{/if}
							</div>

							{#if tab === 'main'}
								<!-- Members sidebar list -->
								<div class="rail-members-label">Members · {selected.member_count}</div>
								{#if membersLoading && !members.length}<p class="rail-muted">Loading…</p>{/if}
								{#each members as member (member.user_id)}
									<div class="member-card">
										<div
											class="member-avatar"
											style="background:{avatarColor(member.display_name)}"
										>
											{initials(member.display_name)}
										</div>
										<div class="member-info">
											<strong
												>{member.is_me
													? member.display_name + ' (you)'
													: member.display_name}</strong
											>
											<span
												>{member.user_id === String(selected.owner_id)
													? 'Owner'
													: member.role}</span
											>
										</div>
										{#if !member.is_me && selected.role !== 'visitor'}
											<button
												class="dm-btn {chatControls.icon}"
												title="Send DM"
												onclick={() => void startMemberDM(member.user_id)}
												aria-label="Send direct message"><MessageCircle size={15} /></button
											>
										{/if}
									</div>
								{/each}
								{#each guestMembers as guest (guest.id)}
									<div class="member-card">
										<div class="member-avatar" style="background:{avatarColor(guest.display_name)}">
											{initials(guest.display_name)}
										</div>
										<div class="member-info">
											<strong>{guest.display_name}{guest.is_me ? ' (you)' : ''}</strong>
											<span>{guest.role === 'owner' ? 'Owner' : 'Guest'}</span>
										</div>
										{#if !guest.is_me && selected.role !== 'visitor'}
											<button
												class="dm-btn {chatControls.icon}"
												title="Send DM"
												onclick={() => void startGuestDM(guest.id)}
												aria-label="Send direct message"><MessageCircle size={15} /></button
											>
										{/if}
									</div>
								{/each}
								{#if hasMoreMembers}
									<button
										class="load-more-members {chatControls.ghost}"
										onclick={() => void loadMembers(true)}>Show more members</button
									>
								{/if}
							{:else if tab === 'members'}
								<!-- Full members list -->
								<div class="rail-members-label">All members · {selected.member_count}</div>
								<p class="rail-muted">
									{guestCount} guest {guestCount === 1 ? 'member' : 'members'}
								</p>
								{#if membersLoading && !members.length}<p class="rail-muted">Loading…</p>{/if}
								{#each members as member (member.user_id)}
									<div class="member-card">
										<div
											class="member-avatar"
											style="background:{avatarColor(member.display_name)}"
										>
											{initials(member.display_name)}
										</div>
										<div class="member-info">
											<strong
												>{member.is_me
													? member.display_name + ' (you)'
													: member.display_name}</strong
											>
											<span
												>{member.user_id === String(selected.owner_id)
													? 'Owner'
													: member.role}</span
											>
										</div>
										<div class="member-actions">
											{#if !member.is_me && selected.role !== 'visitor'}
												<button
													class="action-chip {chatControls.ghost}"
													onclick={() => void startMemberDM(member.user_id)}>DM</button
												>
											{/if}
											{#if selected.role === 'owner' && member.user_id !== String(selected.owner_id)}
												<button
													class="action-chip {chatControls.ghost}"
													onclick={() =>
														void action(
															`/communities/${activeCommunityId()}/members/${member.user_id}`,
															'PATCH',
															{ role: member.role === 'moderator' ? 'member' : 'moderator' }
														)}>{member.role === 'moderator' ? 'Demote' : 'Mod'}</button
												>
											{/if}
											{#if (selected.role === 'owner' || selected.role === 'moderator') && member.user_id !== String(selected.owner_id) && (member.role !== 'moderator' || selected.role === 'owner')}
												<button
													class="action-chip danger {chatControls.danger}"
													onclick={() =>
														void action(
															`/communities/${activeCommunityId()}/members/${member.user_id}`,
															'DELETE'
														)}>Kick</button
												>
												<button
													class="action-chip danger {chatControls.danger}"
													onclick={() =>
														void action(`/communities/${activeCommunityId()}/moderation`, 'POST', {
															user_id: member.user_id,
															action: 'ban'
														})}>Ban</button
												>
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
											<strong>{guest.display_name}{guest.is_me ? ' (you)' : ''}</strong>
											<span>{guest.role === 'owner' ? 'Owner' : 'Guest'}</span>
										</div>
										{#if !guest.is_me && selected.role !== 'visitor'}
											<button
												class="action-chip {chatControls.ghost}"
												onclick={() => void startGuestDM(guest.id)}>DM</button
											>
										{/if}
									</div>
								{/each}
								{#if hasMoreMembers}
									<button
										class="load-more-members {chatControls.ghost}"
										onclick={() => void loadMembers(true)}>Load more</button
									>
								{/if}
								{#if selected.role === 'owner' && transferableMembers.length}
									<div class="transfer-section">
										<p class="rail-muted">Transfer ownership:</p>
										<form
											onsubmit={(e) => {
												e.preventDefault();
												const sel = (e.currentTarget as HTMLFormElement).querySelector('select');
												if (sel)
													void action(`/communities/${activeCommunityId()}/transfer`, 'POST', {
														user_id: sel.value
													});
											}}
										>
											<NativeSelect required aria-label="New owner">
												<option value="" disabled selected>Choose a member</option>
												{#each transferableMembers as m (m.user_id)}<option value={m.user_id}
														>{m.display_name}</option
													>{/each}
											</NativeSelect>
											<button class="btn-sm-primary {chatControls.primary}" style="margin-top:8px"
												>Transfer ownership</button
											>
										</form>
									</div>
								{/if}
							{:else}
								<!-- Settings panel -->
								<dialog
									class="manage-dialog"
									aria-labelledby="manage-title"
									{@attach (node) => {
										node.showModal();
									}}
									onclose={() => (tab = 'main')}
								>
									<header class="manage-header">
										<div>
											<small>{selected.name}</small>
											<h2 id="manage-title">Community settings</h2>
										</div>
										<button
											class="chat-icon {chatControls.icon}"
											aria-label="Close community settings"
											onclick={(event) => event.currentTarget.closest('dialog')?.close()}
											><X size={18} /></button
										>
									</header>
									<div class="settings-panel">
										{#if error}<p role="alert">{error}</p>{/if}
										<Card.Root class="settings-section">
											<div class="settings-section-head">Community details</div>
											{#if selected.role === 'owner'}
												<p class="save-status" role="status">{detailsStatus || 'Auto-saves'}</p>
												<label
													>Name<Input
														required
														maxlength={100}
														bind:value={name}
														onblur={() => void saveDetails()}
													/></label
												>
												<label
													>Description<Textarea
														maxlength={1000}
														bind:value={description}
														onblur={() => void saveDetails()}
													></Textarea></label
												>
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
											{:else}<p>{selected.description || selected.name}</p>
												<small
													>{[selected.school, selected.course].filter(Boolean).join(' · ')}</small
												>{/if}
										</Card.Root>
										<Card.Root class="settings-section">
											<div class="settings-section-head">Invite links</div>
											<p class="rail-muted">Invite classmates to this community.</p>
											<button
												class="btn-sm-primary {chatControls.primary}"
												onclick={() => void createInvite()}
												>Create 7-day invite to selected channel</button
											>
											{@render generatedInvite()}
											{#each invites as invite (invite.id)}
												<div class="invite-row">
													<span
														>#{invite.id} · {invite.uses}{invite.max_uses
															? `/${invite.max_uses}`
															: ''} uses{invite.revoked ? ' · Revoked' : ''}</span
													>
													{#if !invite.revoked}
														<button
															class="action-chip danger {chatControls.danger}"
															onclick={() =>
																void action(
																	`/communities/${activeCommunityId()}/invites/${invite.id}`,
																	'DELETE'
																)}>Revoke</button
														>
													{/if}
												</div>
											{/each}
											{#if selected.role === 'owner' || selected.role === 'moderator'}
												<div class="settings-share-row">
													<button
														class="btn-sm-outline {chatControls.outline}"
														onclick={() => void shareChannel()}>Copy channel link</button
													>
													{#if copyStatus}<p role="status">{copyStatus}</p>{/if}
													{#if shareLink}<Input
															aria-label="Shareable channel URL"
															readonly
															value={shareLink}
															onclick={(e) => e.currentTarget.select()}
														/>{/if}
												</div>
											{/if}
										</Card.Root>
										{#if selected.role === 'owner'}
											<Card.Root class="settings-section">
												<div class="settings-section-head">Danger zone</div>
												<p class="rail-muted">
													Deleting this community removes its channels and conversations.
												</p>
												<button
													class="btn-danger-outline {chatControls.danger}"
													onclick={() => void deleteCommunity()}>Delete community</button
												>
											</Card.Root>
										{/if}
									</div>
								</dialog>
							{/if}
						</aside>
					</div>
				{:else}
					<!-- Landing page -->
					<div class="landing">
						<div class="landing-hero">
							<p class="landing-eyebrow">StudySpot Communities</p>
							<h1>Find your people.<br />Make progress<br />together.</h1>
							<p class="landing-lead">
								Join a public study group, pick a channel, and start talking. Or create a space for
								the course you're working through.
							</p>
							<div class="landing-cta">
								<button class="btn-primary {chatControls.primary}" onclick={showCreate}
									>Create a community</button
								>
								<button
									class="landing-cta-secondary {chatControls.outline}"
									onclick={async () => {
										navOpen = true;
										await tick();
										document.getElementById('community-search')?.focus();
									}}
								>
									Browse communities
								</button>
							</div>
						</div>

						<div class="landing-features">
							<Card.Root class="feature-card">
								<span class="feature-icon" aria-hidden="true"><Hash size={20} /></span>
								<strong>Organized channels</strong>
								<p>Keep homework, exam prep, and casual chat in separate channels.</p>
							</Card.Root>
							<Card.Root class="feature-card">
								<span class="feature-icon" aria-hidden="true"><MessageCircle size={20} /></span>
								<strong>Direct messages</strong>
								<p>Message any member privately, outside of group channels.</p>
							</Card.Root>
							<Card.Root class="feature-card">
								<span class="feature-icon" aria-hidden="true"><Link2 size={20} /></span>
								<strong>Invite links</strong>
								<p>Share a link to bring classmates into your public community.</p>
							</Card.Root>
						</div>

						<h2 class="explore-heading">Explore communities</h2>
						<div class="community-grid">
							{#each communities.slice(0, 6) as community (community.id)}
								<button
									class="community-card {chatControls.row}"
									disabled={joining !== null}
									aria-label={(community.role === 'visitor' ? 'Join ' : 'Open ') + community.name}
									oncontextmenu={(e) => openCommunityMenu(e, community)}
									onclick={() => void enterFromExplore(community)}
								>
									<div class="community-card-icon" style="background:{avatarColor(community.name)}">
										{initials(community.name)}
									</div>
									<div class="community-card-info">
										<strong>{community.name}</strong>
										<span
											>{[community.school, community.course].filter(Boolean).join(' · ') ||
												'Open study community'}</span
										>
										<small
											>{community.member_count}
											{community.member_count === 1 ? 'member' : 'members'} · Public</small
										>
										<b class="card-action"
											>{joining === community.id
												? 'Opening…'
												: community.role === 'visitor'
													? 'Join community →'
													: 'Open community →'}</b
										>
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
	.site-navigation {
		padding: 0 clamp(10px, 3vw, 40px);
		background: white;
	}
	.site-navigation[data-theme='dark'] {
		--site-menu-bg: #2b2d31;
		--site-menu-border: #41434a;
		background: #1e1f22;
		--color-brand-hover: #a4acff;
	}
	.site-navigation[data-theme='dark'] :global(.nav-link) {
		background: #2b2d31;
		color: #f2f3f5;
		border-color: #41434a;
	}
	.community-pop {
		position: fixed;
		inset: auto;
		margin: 0;
		width: min(224px, 95vw);
		padding: 8px;
		background: var(--panel);
		color: var(--ink);
		border: 1px solid var(--line);
		border-radius: 12px;
		box-shadow: 0 8px 28px #0003;
	}
	.community-pop:popover-open,
	.flow-dialog[open] {
		display: grid;
		gap: 4px;
	}
	.community-pop strong,
	.community-pop button {
		padding: 7px 10px;
		text-align: left;
		overflow-wrap: anywhere;
	}
	.community-pop button:hover,
	.community-pop button:focus-visible {
		background: var(--well);
		border-radius: 6px;
	}
	.flow-dialog[open] {
		gap: 12px;
	}

	/* ── Shell ── */
	.shell {
		min-height: 100vh;
		background: var(--panel);
	}

	.auth-loading {
		display: flex;
		align-items: center;
		justify-content: center;
		height: 100dvh;
	}
	.auth-spinner {
		width: 32px;
		height: 32px;
		border: 3px solid var(--line);
		border-top-color: var(--accent);
		border-radius: 50%;
		animation: spin 0.7s linear infinite;
	}
	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}
	main {
		height: 100dvh;
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
	.sidebar-search-row :global(input) {
		width: 100%;
		background: var(--panel);
		border: 1px solid var(--sb-border);
		border-radius: 8px;
		color: var(--sb-text);
		padding: 7px 10px;
		font: inherit;
		font-size: 13px;
		box-sizing: border-box;
		transition: border-color 0.15s;
	}
	.sidebar-search-row :global(input::placeholder) {
		color: var(--sb-muted);
	}
	.sidebar-search-row :global(input:focus) {
		outline: none;
		border-color: var(--accent);
		box-shadow: 0 0 0 2px var(--selected);
	}
	.sidebar-tabs {
		display: flex;
		gap: 2px;
		background: rgba(0, 0, 0, 0.06);
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
		transition:
			background 0.12s,
			color 0.12s;
	}
	.sidebar-tabs button.chosen {
		color: var(--accent-text);
		background: var(--panel);
	}
	.sidebar-tabs button:hover:not(.chosen) {
		color: var(--sb-text);
	}

	.sidebar-scroll {
		flex: 1;
		min-height: 0;
		overflow-y: auto;
	}
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
		transition:
			background 0.1s,
			color 0.1s;
		border-left: 2px solid transparent;
	}
	.sidebar-item:hover {
		background: var(--sb-hover);
	}
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
	.sidebar-item.active .sidebar-item-name {
		color: var(--sb-text-act);
	}
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
	.sidebar-load-more:hover {
		color: var(--sb-text);
	}

	.sidebar-muted {
		font-size: 12px;
		color: var(--sb-muted);
		padding: 4px 14px;
		margin: 0;
	}

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
		background: var(--control-primary);
		color: white;
		font: inherit;
		font-size: 13px;
		font-weight: 700;
		cursor: pointer;
		transition: background 0.12s;
		text-align: center;
	}
	.create-btn:hover {
		background: var(--control-primary-hover);
	}

	/* ── Content area ── */
	.content {
		display: flex;
		flex-direction: column;
		min-width: 0;
		min-height: 0;
		overflow-y: auto;
		background: var(--panel);
	}
	.content.workspace-mode {
		overflow: hidden;
	}

	.error-banner {
		padding: 10px 20px;
		background: var(--accent-lt);
		color: var(--accent);
		font-size: 13px;
		border-bottom: 1px solid var(--selected);
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
		transition:
			color 0.1s,
			background 0.1s;
	}
	.rail-add-btn:hover {
		color: var(--sb-text);
		background: var(--sb-hover);
	}
	.rail-add-btn:disabled {
		opacity: 0.4;
		cursor: default;
	}

	.channel-create-form {
		margin: 6px 4px 10px;
		padding: 10px;
		background: rgba(0, 0, 0, 0.04);
		border-radius: 8px;
	}
	.channel-create-form :global(input) {
		width: 100%;
		background: var(--panel);
		border: 1px solid var(--sb-border);
		border-radius: 6px;
		padding: 6px 8px;
		font: inherit;
		font-size: 13px;
		color: var(--ink);
		box-sizing: border-box;
	}
	.channel-create-form :global(input:focus) {
		outline: none;
		border-color: var(--accent);
		box-shadow: 0 0 0 2px var(--selected);
	}
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
		background: var(--panel);
		color: var(--sb-text);
		cursor: pointer;
		font: inherit;
		font-size: 12px;
		font-weight: 600;
		transition: background 0.1s;
	}
	.mini-actions button:hover {
		background: var(--sb-hover);
	}
	.btn-sm-primary {
		background: var(--accent) !important;
		color: white !important;
	}
	.btn-sm-primary:hover:not([disabled]) {
		background: var(--accent-h) !important;
	}

	.channel-list {
		list-style: none;
		margin: 0;
		padding: 0;
		display: grid;
		gap: 1px;
	}
	.channel-item {
		position: relative;
	}
	.channel-row {
		display: flex;
		align-items: center;
		border-radius: 6px;
		transition: background 0.1s;
	}
	.channel-row:hover {
		background: var(--sb-hover);
	}
	.channel-row.active {
		background: var(--sb-active);
	}
	.channel-row.archived .ch-name {
		opacity: 0.5;
	}

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
	.channel-row:hover .channel-btn {
		color: var(--sb-text);
	}
	.channel-row.active .channel-btn {
		color: var(--sb-text-act);
		font-weight: 600;
	}
	.ch-name {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.archived-chip {
		font-size: 9px;
		background: rgba(0, 0, 0, 0.07);
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
		transition:
			opacity 0.1s,
			background 0.1s,
			color 0.1s;
		padding: 0;
	}
	.channel-row:hover .ch-options-btn,
	.channel-row:focus-within .ch-options-btn {
		opacity: 1;
	}
	@media (hover: none) {
		.channel-row .ch-options-btn {
			opacity: 1;
		}
	}
	.ch-options-btn:hover {
		background: var(--sb-active);
		color: var(--sb-text-act);
	}

	.channel-menu {
		position: absolute;
		top: 36px;
		right: 0;
		z-index: 10;
		background: var(--panel);
		border: 1px solid var(--sb-border);
		border-radius: 10px;
		padding: 4px;
		min-width: 160px;
		box-shadow:
			0 8px 24px rgba(0, 0, 0, 0.12),
			0 0 0 1px rgba(0, 0, 0, 0.05);
		animation: fadeIn 0.1s ease;
	}
	.channel-menu button {
		display: block;
		width: 100%;
		text-align: left;
		border: 0;
		background: transparent;
		color: var(--ink);
		padding: 8px 10px;
		font: inherit;
		font-size: 13px;
		border-radius: 6px;
		cursor: pointer;
		transition: background 0.1s;
	}
	.channel-menu button:hover {
		background: var(--sb-hover);
	}
	.menu-danger {
		color: var(--danger) !important;
	}
	.menu-danger:hover {
		background: rgba(192, 57, 43, 0.08) !important;
	}

	.rail-actions {
		padding: 8px 10px 14px;
		margin-top: auto;
		flex-shrink: 0;
	}
	.rail-join-btn,
	.rail-leave-btn {
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
	.rail-join-btn {
		background: var(--accent);
		color: white;
		border: none;
	}
	.rail-join-btn:hover {
		background: var(--accent-h);
	}
	.rail-leave-btn {
		background: rgba(0, 0, 0, 0.05);
		color: var(--sb-text);
		border: none;
	}
	.rail-leave-btn:hover {
		background: rgba(0, 0, 0, 0.09);
		color: var(--ink);
	}

	/* Chat area */
	.chat-area {
		display: flex;
		flex-direction: column;
		min-width: 0;
		min-height: 0;
		overflow: hidden;
		background: var(--panel);
	}
	.channel-pane {
		display: flex;
		flex-direction: column;
		flex: 1;
		min-height: 0;
	}
	.channel-edit-bar {
		padding: 10px 20px;
		background: var(--selected);
		border-bottom: 1px solid var(--line);
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
		color: var(--ink);
	}
	.channel-edit-bar :global(input) {
		border: 1px solid var(--line);
		border-radius: 4px;
		padding: 5px 8px;
		font: inherit;
		font-size: 13px;
		width: 160px;
	}
	.channel-edit-bar :global(input:focus) {
		outline: none;
		border-color: var(--accent);
		box-shadow: 0 0 0 2px var(--selected);
	}
	.save-hint {
		font-size: 11px;
		color: var(--muted);
	}
	.btn-danger-sm {
		color: var(--danger) !important;
		background: transparent !important;
	}

	.share-banner {
		padding: 8px 20px;
		background: var(--selected);
		border-bottom: 1px solid var(--line);
		flex-shrink: 0;
	}
	.share-msg {
		margin: 0 0 4px;
		font-size: 13px;
		color: var(--success);
	}
	.share-link {
		width: 100%;
		border: 1px solid var(--line);
		border-radius: 6px;
		padding: 6px 10px;
		font: inherit;
		font-size: 12px;
		background: var(--panel);
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
	.join-wall h3 {
		margin: 0 0 8px;
		font-size: 22px;
		color: var(--ink);
	}
	.join-wall p {
		color: var(--muted);
		margin: 0 0 20px;
	}

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
		color: var(--line);
		margin-bottom: 16px;
	}
	.empty-channel h3 {
		margin: 0 0 8px;
		color: var(--ink);
	}
	.empty-channel p {
		color: var(--muted);
		margin: 0 0 20px;
	}

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
		transition:
			background 0.1s,
			color 0.1s;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.tab-link:hover {
		background: var(--sb-hover);
		color: var(--sb-text);
	}
	.tab-link.chosen {
		background: var(--sb-active);
		color: var(--sb-text-act);
	}

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
	.member-card:hover {
		background: var(--sb-hover);
	}
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
		transition:
			opacity 0.1s,
			background 0.1s;
		min-height: 0;
		flex-shrink: 0;
	}
	.member-card:hover .dm-btn {
		opacity: 1;
	}
	.dm-btn:hover {
		background: var(--sb-active);
		color: var(--sb-text-act);
	}

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
		transition:
			background 0.1s,
			color 0.1s;
		font: inherit;
		font-size: 11px;
		font-weight: 600;
	}
	.action-chip:hover {
		background: var(--sb-hover);
		color: var(--sb-text);
	}
	.action-chip.danger {
		color: var(--danger);
		border-color: rgba(192, 57, 43, 0.3);
	}
	.action-chip.danger:hover {
		background: rgba(192, 57, 43, 0.08);
	}

	.load-more-members {
		display: block;
		width: calc(100% - 24px);
		margin: 4px 12px;
		padding: 6px;
		border: 0;
		border-radius: 6px;
		background: rgba(0, 0, 0, 0.04);
		color: var(--sb-muted);
		font: inherit;
		font-size: 12px;
		cursor: pointer;
		transition: background 0.1s;
	}
	.load-more-members:hover {
		background: var(--sb-hover);
		color: var(--sb-text);
	}

	.transfer-section {
		padding: 12px;
		border-top: 1px solid var(--sb-border);
		margin-top: 8px;
	}
	.transfer-section :global(select) {
		width: 100%;
		background: var(--panel);
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
	:global(.settings-section) {
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
	:global(.settings-section) label {
		display: block;
		font-size: 11px;
		font-weight: 700;
		color: var(--sb-muted);
		text-transform: uppercase;
		letter-spacing: 0.05em;
		margin: 10px 0 4px;
	}
	.manage-dialog :global(.settings-section input),
	.manage-dialog :global(.settings-section textarea) {
		width: 100%;
		background: var(--panel);
		border: 1px solid var(--sb-border);
		color: var(--ink);
		border-radius: 6px;
		padding: 7px 8px;
		font: inherit;
		font-size: 13px;
		box-sizing: border-box;
	}
	.manage-dialog :global(.settings-section textarea) {
		min-height: 80px;
		resize: vertical;
	}
	.manage-dialog :global(.settings-section input:focus),
	.manage-dialog :global(.settings-section textarea:focus) {
		outline: none;
		border-color: var(--accent);
		box-shadow: 0 0 0 2px var(--selected);
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
		background: var(--panel);
		color: var(--sb-text);
		cursor: pointer;
		font: inherit;
		font-weight: 600;
		transition: background 0.1s;
	}
	.btn-sm-outline:hover {
		background: var(--sb-hover);
	}
	.btn-danger-outline {
		width: 100%;
		padding: 8px;
		border: 1px solid rgba(192, 57, 43, 0.4);
		border-radius: 6px;
		background: transparent;
		color: var(--danger);
		font: inherit;
		font-size: 13px;
		font-weight: 600;
		cursor: pointer;
		transition: background 0.1s;
	}
	.btn-danger-outline:hover {
		background: rgba(192, 57, 43, 0.08);
	}

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
	.form-page-inner h2 {
		margin: 0 0 6px;
		font-size: 28px;
		font-weight: 800;
		letter-spacing: -0.03em;
		color: var(--ink);
	}
	.form-lead {
		color: var(--muted);
		margin: 0 0 28px;
		font-size: 15px;
	}
	.form-page-inner label {
		display: block;
		font-size: 13px;
		font-weight: 700;
		margin: 18px 0 6px;
		color: var(--ink);
	}
	.form-page-inner label span {
		display: block;
		font-size: 12px;
		font-weight: 700;
		color: var(--muted);
		text-transform: uppercase;
		letter-spacing: 0.05em;
		margin-bottom: 6px;
	}
	.form-page-inner :global(input),
	.form-page-inner :global(textarea) {
		width: 100%;
		border: 1px solid var(--line);
		border-radius: 4px;
		padding: 10px 12px;
		font: inherit;
		font-size: 14px;
		transition:
			border-color 0.15s,
			box-shadow 0.15s;
		box-sizing: border-box;
		color: var(--ink);
	}
	.form-page-inner :global(textarea) {
		min-height: 100px;
		resize: vertical;
	}
	.form-page-inner :global(input:focus),
	.form-page-inner :global(textarea:focus) {
		outline: none;
		border-color: var(--accent);
		box-shadow: 0 0 0 2px var(--selected);
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
		border: 1px solid var(--line);
		border-radius: 4px;
		background: var(--panel);
		padding: 10px 22px;
		font: inherit;
		font-size: 14px;
		font-weight: 600;
		transition:
			background 0.1s,
			border-color 0.1s;
		color: var(--ink);
	}
	.form-actions button:hover {
		background: var(--well);
	}
	.btn-primary {
		background: var(--control-primary) !important;
		color: white !important;
		border-color: var(--control-primary) !important;
	}
	.btn-primary:hover {
		background: var(--control-primary-hover) !important;
		border-color: var(--control-primary-hover) !important;
	}
	.btn-danger {
		background: var(--danger) !important;
		color: white !important;
		border-color: var(--danger) !important;
	}

	.confirm-dialog {
		margin: auto;
		max-height: 85dvh;
		overflow: auto;
		background: var(--panel);
		color: var(--ink);
		width: min(420px, calc(100vw - 32px));
		padding: 28px;
		border: 1px solid var(--line);
		border-radius: 8px;
		box-shadow:
			0 0 0 1px rgba(0, 0, 0, 0.08),
			0 20px 60px rgba(0, 0, 0, 0.18);
	}
	.confirm-dialog::backdrop {
		background: rgba(0, 0, 0, 0.5);
	}
	.confirm-dialog h2 {
		font-size: 22px;
		margin: 0 0 8px;
		color: var(--ink);
	}
	.confirm-dialog p {
		color: var(--muted);
		margin: 0 0 20px;
	}

	/* Communities landing page */
	.landing {
		padding: 60px 56px 80px;
		max-width: 1000px;
	}
	.landing-eyebrow {
		font-size: 11px;
		font-weight: 800;
		text-transform: uppercase;
		letter-spacing: 0.1em;
		color: var(--accent-text);
		margin: 0 0 16px;
	}
	.landing h1 {
		font-size: clamp(38px, 5vw, 64px);
		line-height: 1.02;
		letter-spacing: -0.04em;
		margin: 0 0 20px;
		max-width: 680px;
		color: var(--ink);
		font-weight: 800;
	}
	.landing-lead {
		font-size: 17px;
		color: var(--muted);
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
	.landing-cta button {
		min-height: 44px;
		padding-inline: 22px;
		font-size: 15px;
	}
	.landing-cta-secondary {
		background: var(--panel);
		border-color: var(--line);
		color: var(--ink);
	}
	.landing-cta-secondary:hover {
		background: var(--well);
	}

	.landing-features {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(min(100%, 13rem), 1fr));
		gap: 16px;
		margin-bottom: 56px;
	}
	.landing :global(.feature-card) {
		padding: 22px;
		border: 1px solid var(--line);
		border-radius: 12px;
		gap: 8px;
		background: var(--well);
		transition: box-shadow 0.15s;
	}
	.landing :global(.feature-card):hover {
		box-shadow:
			0 0 0 1px rgba(0, 0, 0, 0.1),
			0 4px 12px rgba(0, 0, 0, 0.06);
	}
	.feature-icon {
		display: inline-grid;
		place-items: center;
		inline-size: 32px;
		block-size: 32px;
		background: var(--side);
		border-radius: 8px;
		margin-bottom: 4px;
		color: var(--accent);
	}
	.landing :global(.feature-card strong) {
		display: block;
		font-size: 15px;
		margin: 0;
		color: var(--ink);
	}
	.landing :global(.feature-card p) {
		margin: 0;
		font-size: 13px;
		color: var(--muted);
		line-height: 1.55;
	}

	.explore-heading {
		font-size: 20px;
		font-weight: 700;
		margin: 0 0 16px;
		letter-spacing: -0.025em;
		color: var(--ink);
	}
	.community-grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(min(100%, 16rem), 1fr));
		gap: 12px;
	}
	.community-card {
		display: flex;
		align-items: center;
		gap: 14px;
		text-align: left;
		padding: 18px;
		border: 1px solid var(--line);
		border-radius: 4px;
		background: var(--panel);
		cursor: pointer;
		transition:
			border-color 0.15s,
			box-shadow 0.15s;
		font: inherit;
	}
	.community-card:hover {
		border-color: var(--muted);
		box-shadow:
			0 0 0 1px rgba(0, 0, 0, 0.06),
			0 4px 12px rgba(0, 0, 0, 0.06);
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
	.card-action {
		color: var(--accent-text);
		font-size: 13px;
		margin-top: 5px;
	}
	.community-card-info strong {
		font-size: 14px;
		font-weight: 700;
		color: var(--ink);
	}
	.community-card-info span {
		font-size: 12px;
		color: var(--muted);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.community-card-info small {
		font-size: 11px;
		color: var(--muted);
	}

	.muted {
		color: var(--muted);
		font-size: 13px;
	}

	/* ── Animations ── */
	@keyframes fadeIn {
		from {
			opacity: 0;
			transform: translateY(-4px);
		}
		to {
			opacity: 1;
			transform: translateY(0);
		}
	}

	/* ── Focus ── */
	button:focus-visible,
	.shell :global(input:focus-visible),
	.shell :global(textarea:focus-visible),
	.shell :global(select:focus-visible) {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}
	button:disabled {
		opacity: 0.5;
		cursor: default;
	}

	/* Keep the active conversation wide while retaining one-click room switching. */
	.room-bar {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		padding: 0 1rem;
		border-bottom: 1px solid var(--sb-border);
		font-size: 0.85rem;
	}
	.room-bar :global(details[open]) {
		background: var(--panel);
		box-shadow: 0 4px 16px #0002;
		z-index: 4;
	}
	/* ── Responsive ── */
	@media (max-width: 1200px) {
		.workspace {
			grid-template-columns: 200px minmax(0, 1fr) 210px;
		}
	}
	@media (max-width: 1050px) {
		.workspace {
			grid-template-columns: 180px minmax(0, 1fr) 190px;
		}
		.landing {
			padding: 40px 36px 60px;
		}
	}
	@media (max-width: 1120px) {
		.workspace {
			grid-template-columns: 180px minmax(0, 1fr);
		}
		.member-rail {
			display: none;
		}
	}
	@media (max-width: 740px) {
		main {
			display: block;
			height: auto;
		}
		.workspace {
			display: block;
		}
		.channel-rail {
			border-right: 0;
			border-bottom: 1px solid var(--sb-border);
		}
		.landing {
			padding: 28px 22px 48px;
		}
		.community-grid {
			grid-template-columns: 1fr;
		}
	}
</style>
