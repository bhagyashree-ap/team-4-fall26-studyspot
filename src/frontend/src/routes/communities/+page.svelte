<script lang="ts">
	import SiteHeader from '$lib/SiteHeader.svelte';
	import CommunityDiscovery from '$lib/CommunityDiscovery.svelte';
	import { chatControls } from '$lib/chatControls';
	import { Input } from '$lib/components/ui/input';
	import { Textarea } from '$lib/components/ui/textarea';
	import { NativeSelect } from '$lib/components/ui/native-select';
	import { base, resolve } from '$app/paths';
	import { goto } from '$app/navigation';
	import { onMount, tick } from 'svelte';
	import * as Card from '$lib/components/ui/card';
	import X from '@lucide/svelte/icons/x';
	import Moon from '@lucide/svelte/icons/moon';
	import Sun from '@lucide/svelte/icons/sun';
	import ArrowLeft from '@lucide/svelte/icons/arrow-left';
	import Hash from '@lucide/svelte/icons/hash';
	import MessagesSquare from '@lucide/svelte/icons/messages-square';
	import Send from '@lucide/svelte/icons/send';
	import Link2 from '@lucide/svelte/icons/link-2';
	import Users from '@lucide/svelte/icons/users';
	import Plus from '@lucide/svelte/icons/plus';
	import LockKeyhole from '@lucide/svelte/icons/lock-keyhole';
	import ChevronDown from '@lucide/svelte/icons/chevron-down';
	import UserRound from '@lucide/svelte/icons/user-round';
	import Trash2 from '@lucide/svelte/icons/trash-2';
	import Settings from '@lucide/svelte/icons/settings';
	import Bell from '@lucide/svelte/icons/bell';
	import '$lib/chat-theme.css';
	import Autocomplete from '$lib/Autocomplete.svelte';
	import { channelLink } from '$lib/chatLinks';
	import ChatInbox from '$lib/ChatInbox.svelte';
	import CommunityNotificationSettings from '$lib/CommunityNotificationSettings.svelte';
	import ChannelChat from '$lib/ChannelChat.svelte';
	import {
		communityRequest,
		type Channel,
		type Community,
		type DirectConversation,
		type GuestMember,
		type Invite,
		type Member,
		type MemberPresence
	} from '$lib/communities';
	import { session } from '$lib/session.svelte';

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
	let contentElement = $state<HTMLDivElement>();
	let communities = $state<Community[]>([]);
	let selected = $state<Community | null>(null);
	let members = $state<Member[]>([]);
	let guestMembers = $state<GuestMember[]>([]);
	let accountPresence = $state<Record<string, MemberPresence>>({});
	let guestPresence = $state<Record<string, MemberPresence>>({});
	let memberProfile = $state<{
		name: string;
		role: string;
		joinedAt: string | null;
		presence: MemberPresence | null;
		userId: string | null;
		guestMemberId: number | null;
		isMe: boolean;
	} | null>(null);
	let profilePosition = $state({ left: 12, top: 12 });
	let profileRequest = 0;
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
	let channelPassword = $state('');
	let unlockPassword = $state('');
	let unlockingChannel = $state(false);
	let channelCreateOpen = $state(false);
	let channelMenuOpen = $state<number | null>(null);
	let channelMenuLeft = $state(0);
	let channelMenuTop = $state(0);
	let accountMenuOpen = $state(false);
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
	let membersOpen = $state(false);
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
		channelsOpen = false;
		membersOpen = false;
		memberProfile = null;
		const initial = new URL(location.href);
		const hash =
			Number(initial.searchParams.get('id')) === id &&
			Number(initial.searchParams.get('channel')) === channelId
				? initial.hash
				: '';
		error = '';
		try {
			selected = await communityRequest<Community>(`/communities/${id}`);
			channelCreateOpen = false;
			accountPresence = {};
			guestPresence = {};
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

	function openInbox() {
		const returnTo = selected
			? `${resolve('/communities')}?id=${selected.id}${activeChannelId ? `&channel=${activeChannelId}` : ''}`
			: resolve('/communities');
		const returnContext = `returnTo=${encodeURIComponent(returnTo)}&returnLabel=${encodeURIComponent(selected?.name ?? 'Communities')}`;
		void goto(resolve(`/messages?${returnContext}`));
	}
	function openDM(conversation: DirectConversation) {
		const returnTo = selected
			? `${resolve('/communities')}?id=${selected.id}${activeChannelId ? `&channel=${activeChannelId}` : ''}`
			: resolve('/communities');
		const returnContext = `returnTo=${encodeURIComponent(returnTo)}&returnLabel=${encodeURIComponent(selected?.name ?? 'Communities')}`;
		void goto(resolve(`/messages?dm=${conversation.id}&${returnContext}`));
	}

	function goHome() {
		channelsOpen = false;
		selected = null;
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
				{ name: channelName, ...(channelPassword ? { password: channelPassword } : {}) }
			);
			channelName = channelPassword = '';
			await choose(selected.id, created.id);
			await tick();
			document.getElementById(`channel-select-${created.id}`)?.focus();
		} catch (cause) {
			error = message(cause);
		}
	}

	async function openChannelCreate() {
		channelMenuOpen = null;
		channelPassword = '';
		channelCreateOpen = true;
		await tick();
		channelNameInput?.focus();
	}

	async function closeChannelCreate() {
		channelCreateOpen = false;
		channelPassword = '';
		await tick();
		document.getElementById('add-channel-button')?.focus();
	}

	async function toggleChannelMenu(channelId: number, event?: MouseEvent) {
		if (channelMenuOpen === channelId) {
			channelMenuOpen = null;
			return;
		}
		const trigger = event?.currentTarget instanceof HTMLElement ? event.currentTarget : null;
		const bounds = trigger?.getBoundingClientRect();
		const pointer = event?.type === 'contextmenu';
		const left = pointer ? event.clientX : (bounds?.right ?? 0) - 220;
		const top = pointer ? event.clientY : (bounds?.bottom ?? 0) + 6;
		channelMenuLeft = Math.max(8, Math.min(left, innerWidth - 232));
		channelMenuTop = Math.max(8, Math.min(top, innerHeight - 280));
		channelMenuOpen = channelId;
		await tick();
		const menu = document.getElementById(`channel-options-${channelId}`);
		menu?.showPopover();
		menu?.querySelector<HTMLButtonElement>('button')?.focus();
	}

	async function unlockChannel(channel: Channel) {
		if (!selected || unlockingChannel) return;
		unlockingChannel = true;
		error = '';
		try {
			await communityRequest(`/communities/${selected.id}/channels/${channel.id}/unlock`, 'POST', {
				password: unlockPassword
			});
			unlockPassword = '';
			await choose(selected.id, channel.id);
		} catch (cause) {
			error = message(cause);
		} finally {
			unlockingChannel = false;
		}
	}

	async function toggleAccountMenu(event?: MouseEvent) {
		if (event?.type === 'contextmenu') event.preventDefault();
		accountMenuOpen = !accountMenuOpen;
		if (accountMenuOpen) await tick();
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
		if (memberProfile) {
			memberProfile = null;
			return;
		}
		if (accountMenuOpen) {
			accountMenuOpen = false;
			document.querySelector<HTMLButtonElement>('.self-card')?.focus();
			return;
		}
		if (communityMenu?.matches(':popover-open')) {
			communityMenu.hidePopover();
			communityTrigger?.focus();
			return;
		}
		if (
			channelsOpen &&
			channelMenuOpen === null &&
			!channelCreateOpen &&
			editingChannelId === null
		) {
			document.querySelector<HTMLButtonElement>('[aria-controls="channel-navigation"]')?.focus();
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

	async function loadMemberPresence(communityId: number) {
		try {
			const result = await communityRequest<{
				accounts: Record<string, MemberPresence>;
				guests: Record<string, MemberPresence>;
			}>(`/communities/${communityId}/presence`);
			if (selected?.id !== communityId) return;
			accountPresence = result.accounts;
			guestPresence = result.guests;
		} catch {
			// Presence is supplementary; keep the rest of the community usable.
		}
	}

	function findMember(name: string) {
		const account = members.find((member) => member.display_name === name);
		if (account) {
			return {
				name,
				role: account.user_id === String(selected?.owner_id) ? 'owner' : account.role,
				joinedAt: account.joined_at,
				presence: accountPresence[account.user_id] ?? null,
				userId: account.user_id,
				guestMemberId: null,
				isMe: account.is_me
			};
		}
		const guest = guestMembers.find((member) => member.display_name === name);
		if (guest) {
			return {
				name,
				role: guest.role,
				joinedAt: null,
				presence: guestPresence[String(guest.id)] ?? null,
				userId: null,
				guestMemberId: guest.id,
				isMe: guest.is_me
			};
		}
		return null;
	}

	async function openMemberProfile(name: string, event: MouseEvent) {
		event.stopPropagation();
		const requestId = ++profileRequest;
		const targetCommunity = selected?.id;
		const element = event.currentTarget as HTMLElement;
		const bounds = element.getBoundingClientRect();
		const x = event.detail ? event.clientX : bounds.left;
		const y = event.detail ? event.clientY : bounds.bottom;
		profilePosition = {
			left: Math.max(12, Math.min(x + 10, innerWidth - 332)),
			top: Math.max(12, Math.min(y + 10, innerHeight - 410))
		};
		memberProfile = findMember(name) ?? {
			name,
			role: 'member',
			joinedAt: null,
			presence: null,
			userId: null,
			guestMemberId: null,
			isMe: false
		};
		while (!findMember(name) && hasMoreMembers && selected?.id === targetCommunity) {
			const previousOffset = memberOffset;
			await loadMembers(true);
			if (requestId !== profileRequest || memberOffset === previousOffset) return;
		}
		if (requestId === profileRequest) memberProfile = findMember(name) ?? memberProfile;
	}

	$effect(() => {
		const communityId = selected?.id;
		if (!communityId) return;
		void loadMemberPresence(communityId);
		const timer = setInterval(() => void loadMemberPresence(communityId), 30_000);
		return () => clearInterval(timer);
	});

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
		menuLeft = Math.max(4, Math.min(pointer ? event.clientX : rect.left, innerWidth - 300));
		menuTop = Math.max(4, Math.min(pointer ? event.clientY : rect.bottom, innerHeight - 350));
		menuCommunity = community;
		communityMenu?.showPopover();
		void tick()
			.then(() => {
				if (!communityMenu) return;
				menuLeft = Math.max(4, Math.min(menuLeft, innerWidth - communityMenu.offsetWidth - 8));
				menuTop = Math.max(4, Math.min(menuTop, innerHeight - communityMenu.offsetHeight - 8));
				return tick();
			})
			.then(() => communityMenu?.querySelector('button')?.focus());
	}

	async function communityOption(
		option: 'settings' | 'create' | 'leave' | 'invite' | 'members' | 'delete' | 'notifications'
	) {
		const target = menuCommunity;
		communityMenu?.hidePopover();
		if (!target) return;
		if (option === 'leave') {
			accountMenuOpen = false;
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
		if (option === 'members') {
			membersOpen = true;
			tab = 'members';
			await loadMembers();
		}
		if (option === 'delete') {
			await deleteCommunity();
			return;
		}
		if (option === 'settings') {
			membersOpen = true;
			await loadSettings();
		}
		if (option === 'notifications') {
			membersOpen = true;
			await loadSettings();
			await tick();
			document
				.getElementById('community-notifications')
				?.scrollIntoView({ behavior: 'smooth', block: 'start' });
		}
		if (option === 'create') {
			channelsOpen = true;
			await openChannelCreate();
		}
	}

	function runAccountOption(option: 'settings' | 'leave' | 'invite') {
		if (!selected) return;
		menuCommunity = selected;
		accountMenuOpen = false;
		void communityOption(option);
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
					void goto(resolve(`/messages?dm=${dmId}${url.hash}`));
					return;
				} else if (id) {
					await choose(id, channelId);
				}
			} catch (e) {
				error = message(e);
			}
		}
		void enter().catch((e) => (accessError = message(e)));
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
		if (event.target instanceof Element) {
			if (
				memberProfile &&
				!event.target.closest('.member-profile-popover, .profile-author, .member-profile-trigger')
			)
				memberProfile = null;
			if (channelMenuOpen !== null && !event.target.closest('.channel-menu, .channel-row'))
				channelMenuOpen = null;
			if (accountMenuOpen && !event.target.closest('.account-menu-wrap')) accountMenuOpen = false;
		}
	}}
/>

<svelte:head>
	<title>Communities · StudySpot</title>
	<meta name="description" content="Find and create public study communities." />
</svelte:head>

<div
	class="site-navigation"
	class:workspace-active={!!selected}
	data-theme={theme}
	bind:clientHeight={headerHeight}
>
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
		{#if memberProfile}
			<div
				class="member-profile-popover"
				style:left={profilePosition.left + 'px'}
				style:top={profilePosition.top + 'px'}
				role="dialog"
				aria-label={`${memberProfile.name}'s profile`}
				tabindex="-1"
			>
				<div class="profile-cover" style:background={avatarColor(memberProfile.name)}></div>
				<div class="profile-content">
					<div class="profile-avatar" style:background={avatarColor(memberProfile.name)}>
						{initials(memberProfile.name)}
						<span class:online={memberProfile.presence?.online} class="profile-presence-dot"></span>
					</div>
					<div class="profile-name-row">
						<div>
							<h2>{memberProfile.name}</h2>
							<span class="profile-role">{memberProfile.role}</span>
						</div>
						<button
							class="profile-close"
							aria-label="Close profile"
							onclick={() => (memberProfile = null)}><X size={16} /></button
						>
					</div>
					<div class="profile-status" class:online={memberProfile.presence?.online}>
						<span></span>{memberProfile.presence
							? memberProfile.presence.online
								? 'Online'
								: 'Offline'
							: 'Status unavailable'}
						{#if memberProfile.presence?.last_seen && !memberProfile.presence.online}
							<small
								>· last seen {new Date(memberProfile.presence.last_seen).toLocaleString([], {
									dateStyle: 'medium',
									timeStyle: 'short'
								})}</small
							>
						{/if}
					</div>
					<div class="profile-section">
						<h3>About me</h3>
						<p>No bio added yet.</p>
					</div>
					<div class="profile-section profile-details">
						<h3>In this community</h3>
						<div>
							<span>Role</span><strong
								>{memberProfile.role === 'owner'
									? 'Community owner'
									: memberProfile.role === 'moderator'
										? 'Moderator'
										: memberProfile.role === 'member'
											? 'Member'
											: 'Guest'}</strong
							>
						</div>
						{#if memberProfile.joinedAt}<div>
								<span>Member since</span><strong
									>{new Date(memberProfile.joinedAt).toLocaleDateString([], {
										month: 'long',
										year: 'numeric'
									})}</strong
								>
							</div>{/if}
						{#if selected}<div><span>Community</span><strong>{selected.name}</strong></div>{/if}
					</div>
					{#if !memberProfile.isMe && selected?.role !== 'visitor' && (memberProfile.userId || memberProfile.guestMemberId)}
						<button
							class="profile-message"
							onclick={() => {
								const target = memberProfile;
								memberProfile = null;
								if (target?.userId) void startMemberDM(target.userId);
								else if (target?.guestMemberId) void startGuestDM(target.guestMemberId);
							}}><Send size={15} /> Message</button
						>
					{/if}
				</div>
			</div>
		{/if}

		<div
			bind:this={communityMenu}
			popover="manual"
			class="community-pop"
			style:left={menuLeft + 'px'}
			style:top={menuTop + 'px'}
			role="group"
			aria-label="Community actions"
		>
			{#if menuCommunity}
				<div class="community-pop-heading">
					<span class="community-pop-avatar" style:background={avatarColor(menuCommunity.name)}
						>{initials(menuCommunity.name)}</span
					>
					<div>
						<strong>{menuCommunity.name}</strong><small
							>{menuCommunity.school || 'Study community'}{menuCommunity.course
								? ` · ${menuCommunity.course}`
								: ''}</small
						>
					</div>
				</div>
				{#if menuCommunity.description}<p class="community-pop-description">
						{menuCommunity.description}
					</p>{/if}
				<div class="community-pop-divider"></div>
				<span class="community-pop-label">Community</span>
				{#if menuCommunity.role !== 'visitor'}
					<button onclick={() => void communityOption('members')}
						><UserRound size={15} /> Members &amp; roles</button
					>
					<button onclick={() => void communityOption('settings')}
						><Settings size={15} />
						{menuCommunity.role === 'owner' ? 'Edit community' : 'Community settings'}</button
					>
					<button onclick={() => void communityOption('notifications')}
						><Bell size={15} /> Notification settings</button
					>
				{/if}
				{#if menuCommunity.role === 'owner' || menuCommunity.role === 'moderator'}
					<button onclick={() => void communityOption('invite')}
						><Link2 size={15} /> Invite people</button
					>
				{/if}
				{#if menuCommunity.role !== 'visitor'}<button onclick={() => void communityOption('create')}
						><Plus size={15} /> Create channel</button
					>{/if}
				{#if menuCommunity.role === 'visitor'}<button
						onclick={() => void enterFromExplore(menuCommunity!)}
						><Users size={15} /> Join community</button
					>{/if}
				{#if menuCommunity.role === 'owner' || menuCommunity.role === 'member' || menuCommunity.role === 'moderator'}<div
						class="community-pop-divider"
					></div>{/if}
				{#if menuCommunity.role === 'owner'}<button
						class="community-leave"
						onclick={() => void communityOption('delete')}
						><Trash2 size={15} /> Delete community</button
					>{/if}
				{#if menuCommunity.role === 'member' || menuCommunity.role === 'moderator'}<button
						class="community-leave"
						onclick={() => void communityOption('leave')}><X size={15} /> Leave community…</button
					>{/if}
			{/if}
		</div>
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
			class:discovery-mode={!selected && !creating}
			class:in-room={!!selected}
			class:channels-open={channelsOpen}
			class:members-open={membersOpen}
		>
			<!-- ── Main content ── -->
			<div
				class="content"
				bind:this={contentElement}
				tabindex="-1"
				class:workspace-mode={!!selected}
			>
				<header class="room-bar">
					<button class={chatControls.ghost} onclick={goHome}
						><ArrowLeft size={17} /> Back to communities</button
					>
					{#if selected}<button
							class="chat-icon mobile-nav {chatControls.icon}"
							title="Channels"
							aria-label="Toggle channels"
							aria-controls="channel-navigation"
							aria-expanded={channelsOpen}
							onclick={async () => {
								membersOpen = false;
								channelsOpen = !channelsOpen;
								await tick();
								if (channelsOpen)
									document.querySelector<HTMLElement>('#channel-navigation button')?.focus();
							}}><Hash size={18} /></button
						>{/if}
					<button class={chatControls.ghost} onclick={openInbox}
						><MessagesSquare size={17} /> Direct messages</button
					>
					<div class="app-controls">
						{#if selected}<button
								class="chat-icon members-toggle {chatControls.icon}"
								title="Toggle member list"
								aria-label="Toggle member list"
								aria-expanded={membersOpen}
								onclick={() => {
									channelsOpen = false;
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
				{:else if selected}
					<!-- Community workspace -->
					<div class="workspace">
						{#if channelsOpen || membersOpen}
							<button
								class="workspace-scrim"
								aria-label="Close community panel"
								onclick={() => {
									channelsOpen = false;
									membersOpen = false;
								}}
							></button>
						{/if}
						<!-- Channel rail (left) -->
						<nav
							id="channel-navigation"
							class="channel-rail"
							aria-label={`Channels in ${selected.name}`}
						>
							<div class="community-header">
								<button
									class="community-selector"
									aria-label={`Open ${selected.name} navigation`}
									aria-haspopup="true"
									onclick={(event) => selected && openCommunityMenu(event, selected)}
									oncontextmenu={(event) => selected && openCommunityMenu(event, selected)}
								>
									<span
										class="community-avatar"
										style="background:{avatarColor(selected.name)}"
										aria-hidden="true"
									>
										{initials(selected.name)}
									</span>
									<span class="community-header-text">
										<span class="community-name">{selected.name}</span>
										<span class="community-meta"
											>{selected.member_count}
											{selected.member_count === 1 ? 'member' : 'members'}</span
										>
									</span>
									<ChevronDown class="community-selector-chevron" size={15} />
								</button>
							</div>

							<div class="rail-section">
								<div class="rail-section-header">
									<span>Text channels</span>
									{#if selected.role !== 'visitor'}
										<button
											class="rail-add-btn {chatControls.icon}"
											id="add-channel-button"
											aria-label="Create a text channel"
											title={(selected.channels?.length ?? 0) >= 20
												? 'Channel limit reached'
												: 'Create a text channel'}
											disabled={(selected.channels?.length ?? 0) >= 20}
											onclick={() => void openChannelCreate()}><Plus size={17} /></button
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
										<label class="channel-name-label" for="new-channel-name">Channel name</label>
										<Input
											id="new-channel-name"
											bind:ref={channelNameInput}
											required
											pattern="[a-z0-9][a-z0-9-]*"
											maxlength={50}
											bind:value={channelName}
											placeholder="channel-name"
										/>
										<p class="channel-name-hint">Give your group a little corner of its own.</p>
										<label class="channel-password-label" for="new-channel-password">
											<span>Password lock <small>· optional</small></span>
											<Input
												id="new-channel-password"
												type="password"
												minlength={4}
												maxlength={72}
												bind:value={channelPassword}
												placeholder="Add a passphrase"
												autocomplete="new-password"
											/>
										</label>
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
														void toggleChannelMenu(channel.id, e);
													}}
													aria-current={activeChannelId === channel.id ? 'page' : undefined}
													onclick={() => selectChannel(channel.id)}
												>
													{#if channel.password_protected}<LockKeyhole size={15} />{:else}<Hash
															size={17}
														/>{/if}
													<span class="ch-name">{channel.name}</span>
													{#if channel.locked}<span class="locked-chip">Locked</span>{/if}
													{#if channel.archived}<span class="archived-chip">archived</span>{/if}
												</button>
												<button
													class="ch-options-btn {chatControls.icon}"
													id={`channel-trigger-${channel.id}`}
													aria-label={`Options for #${channel.name}`}
													aria-expanded={channelMenuOpen === channel.id}
													aria-controls={`channel-options-${channel.id}`}
													onclick={(event) => void toggleChannelMenu(channel.id, event)}>⋯</button
												>
											</div>
											{#if channelMenuOpen === channel.id}
												<div
													class="channel-menu"
													id={`channel-options-${channel.id}`}
													role="group"
													popover="manual"
													aria-label={`Options for #${channel.name}`}
													style:left={channelMenuLeft + 'px'}
													style:top={channelMenuTop + 'px'}
												>
													<button
														class={chatControls.ghost}
														onclick={() => {
															channelMenuOpen = null;
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
								<div class="account-menu-wrap">
									<button
										class="self-card"
										aria-label="Open your account and community menu"
										aria-expanded={accountMenuOpen}
										onclick={(event) => void toggleAccountMenu(event)}
										oncontextmenu={(event) => void toggleAccountMenu(event)}
									>
										<span style:background={avatarColor(selfName ?? 'You')}
											>{initials(selfName ?? 'You')}</span
										>
										<div>
											<strong>{selfName ?? 'Your account'}</strong>
											<small
												>{selected.role === 'visitor'
													? 'Previewing community'
													: selected.role}</small
											>
										</div>
										<ChevronDown size={15} />
									</button>
									{#if accountMenuOpen}
										<div
											class="account-menu"
											role="group"
											aria-label="Account and community actions"
										>
											<div class="account-menu-heading">
												<strong>{selfName ?? 'Your account'}</strong>
												<span class="role-pill">{selected.role}</span>
											</div>
											<div class="account-profile">
												<span class="account-status-dot"></span><span
													>Studying {selected.course || 'with the community'}</span
												>
											</div>
											<p class="account-bio">
												“Here to learn together, share notes, and keep the study momentum going.”
											</p>
											<div class="account-meta">
												<span>ROLE</span><strong
													>{selected.role === 'owner'
														? 'Community owner'
														: selected.role === 'moderator'
															? 'Moderator'
															: selected.role === 'visitor'
																? 'Guest'
																: 'Member'}</strong
												>
											</div>
											<div class="account-meta">
												<span>COMMUNITY</span><strong>{selected.name}</strong>
											</div>
											{#if selected.role === 'owner' || selected.role === 'moderator'}
												<button onclick={() => runAccountOption('invite')}>Invite people</button>
											{/if}
											{#if selected.role === 'owner' || selected.role === 'moderator'}
												<button onclick={() => runAccountOption('settings')}
													>Manage community</button
												>
											{/if}
											{#if selected.role === 'member' || selected.role === 'moderator'}
												<button class="account-leave" onclick={() => runAccountOption('leave')}>
													Leave community
												</button>
											{:else if selected.role === 'owner'}
												<div class="owner-note">
													Transfer ownership before leaving this community.
												</div>
											{/if}
										</div>
									{/if}
								</div>
								{#if selected.role === 'visitor'}
									<button
										class="rail-join-btn {chatControls.primary}"
										onclick={() => void action(`/communities/${activeCommunityId()}/join`)}
									>
										Join community
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
										{#if channel.locked}
											<div class="locked-channel">
												<div class="locked-channel-icon"><LockKeyhole size={22} /></div>
												<p class="locked-eyebrow">A quieter corner</p>
												<h3>This channel is password locked</h3>
												<p>Ask the person who created it for the passphrase, then come on in.</p>
												<form
													onsubmit={(event) => {
														event.preventDefault();
														void unlockChannel(channel);
													}}
												>
													<Input
														type="password"
														bind:value={unlockPassword}
														placeholder="Enter passphrase"
														aria-label="Channel passphrase"
														autocomplete="current-password"
													/>
													<button
														class="unlock-button"
														disabled={unlockingChannel || !unlockPassword}
													>
														{unlockingChannel ? 'Opening…' : 'Unlock channel'}
													</button>
												</form>
											</div>
										{:else}
											<ChannelChat
												communityId={selected.id}
												{channel}
												role={selected.role}
												names={[...members, ...guestMembers].map((m) => m.display_name)}
												onShare={() => void shareChannel()}
												onDirectMessage={openDM}
												onMemberSelect={openMemberProfile}
											/>
										{/if}
									{/if}
								</div>
							{:else}
								<div class="empty-channel">
									<div class="empty-icon" aria-hidden="true">#</div>
									<h3>No channels yet</h3>
									<p>Create a channel to start organizing conversations.</p>
									{#if selected.role !== 'visitor'}
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
										<button
											class="member-avatar"
											style="background:{avatarColor(member.display_name)}"
											title={`View ${member.display_name}'s profile`}
											onclick={(event) => void openMemberProfile(member.display_name, event)}
										>
											{initials(member.display_name)}
											<span
												class="member-presence-dot"
												class:online={accountPresence[member.user_id]?.online}
											></span>
										</button>
										<div class="member-info">
											<button
												class="member-profile-trigger"
												onclick={(event) => void openMemberProfile(member.display_name, event)}
												aria-haspopup="dialog"
												>{member.is_me
													? member.display_name + ' (you)'
													: member.display_name}</button
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
												aria-label="Send direct message"><Send size={15} /></button
											>
										{/if}
									</div>
								{/each}
								{#each guestMembers as guest (guest.id)}
									<div class="member-card">
										<button
											class="member-avatar"
											style="background:{avatarColor(guest.display_name)}"
											title={`View ${guest.display_name}'s profile`}
											onclick={(event) => void openMemberProfile(guest.display_name, event)}
										>
											{initials(guest.display_name)}
											<span
												class="member-presence-dot"
												class:online={guestPresence[String(guest.id)]?.online}
											></span>
										</button>
										<div class="member-info">
											<button
												class="member-profile-trigger"
												aria-haspopup="dialog"
												onclick={(event) => void openMemberProfile(guest.display_name, event)}
												>{guest.display_name}{guest.is_me ? ' (you)' : ''}</button
											>
											<span>{guest.role === 'owner' ? 'Owner' : 'Guest'}</span>
										</div>
										{#if !guest.is_me && selected.role !== 'visitor'}
											<button
												class="dm-btn {chatControls.icon}"
												title="Send DM"
												onclick={() => void startGuestDM(guest.id)}
												aria-label="Send direct message"><Send size={15} /></button
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
										<button
											class="member-avatar"
											style="background:{avatarColor(member.display_name)}"
											title={`View ${member.display_name}'s profile`}
											onclick={(event) => void openMemberProfile(member.display_name, event)}
										>
											{initials(member.display_name)}
											<span
												class="member-presence-dot"
												class:online={accountPresence[member.user_id]?.online}
											></span>
										</button>
										<div class="member-info">
											<button
												class="member-profile-trigger"
												aria-haspopup="dialog"
												onclick={(event) => void openMemberProfile(member.display_name, event)}
												>{member.is_me
													? member.display_name + ' (you)'
													: member.display_name}</button
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
										<button
											class="member-avatar"
											style="background:{avatarColor(guest.display_name)}"
											title={`View ${guest.display_name}'s profile`}
											onclick={(event) => void openMemberProfile(guest.display_name, event)}
										>
											{initials(guest.display_name)}
											<span
												class="member-presence-dot"
												class:online={guestPresence[String(guest.id)]?.online}
											></span>
										</button>
										<div class="member-info">
											<button
												class="member-profile-trigger"
												aria-haspopup="dialog"
												onclick={(event) => void openMemberProfile(guest.display_name, event)}
												>{guest.display_name}{guest.is_me ? ' (you)' : ''}</button
											>
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
										<CommunityNotificationSettings
											communityId={selected.id}
											channels={selected.channels ?? []}
											role={selected.role}
										/>
										{#if selected.role === 'owner' || selected.role === 'moderator'}
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
										{/if}
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
					<CommunityDiscovery
						{communities}
						bind:query
						bind:mine={viewMine}
						{loading}
						{hasMore}
						{joining}
						{error}
						{theme}
						ontheme={toggleTheme}
						onopen={(community) => void choose(community.id)}
						onjoin={enterFromExplore}
						oncreate={showCreate}
						onmessages={openInbox}
						onbacktotop={(event) => {
							contentElement?.scrollTo({
								top: 0,
								behavior:
									event.detail > 0 && !matchMedia('(prefers-reduced-motion: reduce)').matches
										? 'smooth'
										: 'instant'
							});
							if (event.detail === 0)
								document.getElementById('discovery-title')?.focus({ preventScroll: true });
						}}
						onmore={() => void browse(query, true)}
					/>
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
	.site-navigation.workspace-active {
		background: #f7f5ef;
		--color-brand-hover: #386b58;
	}
	.site-navigation.workspace-active[data-theme='dark'] {
		background: #1d201b;
		--site-menu-bg: #242620;
		--site-menu-border: #3a3e36;
		--color-brand-hover: #b2d4bb;
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
		width: min(304px, 95vw);
		max-height: calc(100dvh - 16px);
		overflow-y: auto;
		padding: 8px;
		background: var(--panel);
		color: var(--ink);
		border: 1px solid var(--line);
		border-radius: 17px;
		box-shadow: 0 16px 40px rgb(30 32 26 / 18%);
	}
	.community-pop:popover-open,
	.flow-dialog[open] {
		display: grid;
		gap: 4px;
	}
	.community-pop:popover-open {
		animation: chat-reveal 160ms var(--ease-out) both;
	}
	.community-pop strong {
		padding: 8px 10px 4px;
		font-size: 11px;
		font-weight: 700;
		letter-spacing: 0.025em;
		color: var(--muted);
		text-transform: uppercase;
		overflow-wrap: anywhere;
	}
	.community-pop-heading {
		display: flex;
		align-items: center;
		gap: 10px;
		padding: 8px 8px 10px;
	}
	.community-pop-heading > div {
		min-width: 0;
	}
	.community-pop-heading strong {
		display: block;
		padding: 0;
		color: var(--ink);
		font-size: 13px;
		letter-spacing: 0;
		text-transform: none;
	}
	.community-pop-heading small {
		display: block;
		margin-top: 3px;
		color: var(--muted);
		font-size: 10px;
		line-height: 1.4;
	}
	.community-pop-avatar {
		width: 36px;
		height: 36px;
		border-radius: 11px;
		display: grid;
		place-items: center;
		flex: none;
		color: white;
		font-size: 12px;
		font-weight: 750;
	}
	.community-pop-divider {
		height: 1px;
		margin: 3px 4px;
		background: var(--line);
	}
	.community-pop-description {
		margin: 0 8px 7px;
		color: var(--muted);
		font-size: 11px;
		line-height: 1.45;
		display: -webkit-box;
		-webkit-line-clamp: 3;
		line-clamp: 3;
		-webkit-box-orient: vertical;
		overflow: hidden;
	}
	.community-pop-label {
		padding: 5px 10px 3px;
		color: var(--muted);
		font-size: 10px;
		font-weight: 750;
		letter-spacing: 0.08em;
		text-transform: uppercase;
	}
	.community-pop .community-leave {
		margin-top: 3px;
		color: var(--danger);
	}
	.community-pop .community-leave:hover {
		background: color-mix(in srgb, var(--danger) 10%, transparent);
	}
	.member-profile-popover {
		position: fixed;
		z-index: 100;
		width: min(320px, calc(100vw - 24px));
		max-height: min(440px, calc(100dvh - 24px));
		overflow-y: auto;
		border: 1px solid var(--line);
		border-radius: 18px;
		background: var(--panel);
		color: var(--ink);
		box-shadow: 0 22px 64px rgb(18 20 18 / 26%);
		animation: chat-reveal 160ms var(--ease-out) both;
	}
	.profile-cover {
		height: 82px;
		opacity: 0.88;
	}
	.profile-content {
		padding: 0 16px 16px;
	}
	.profile-avatar {
		position: relative;
		width: 70px;
		height: 70px;
		margin-top: -34px;
		display: grid;
		place-items: center;
		border: 6px solid var(--panel);
		border-radius: 50%;
		color: white;
		font-size: 21px;
		font-weight: 750;
	}
	.profile-presence-dot,
	.member-presence-dot {
		position: absolute;
		width: 15px;
		height: 15px;
		bottom: 0;
		right: 0;
		border: 3px solid var(--panel);
		border-radius: 50%;
		background: #858b91;
	}
	.profile-presence-dot.online,
	.member-presence-dot.online {
		background: #43b581;
	}
	.profile-name-row {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: 10px;
	}
	.profile-name-row h2 {
		margin: 4px 0 3px;
		font-size: 18px;
		letter-spacing: -0.025em;
	}
	.profile-role {
		padding: 3px 7px;
		border-radius: 999px;
		background: var(--accent-lt);
		color: var(--accent-text);
		font-size: 10px;
		font-weight: 700;
		text-transform: capitalize;
	}
	.profile-close {
		display: grid;
		place-items: center;
		width: 30px;
		height: 30px;
		border: 0;
		border-radius: 9px;
		background: transparent;
		color: var(--muted);
		cursor: pointer;
	}
	.profile-close:hover {
		background: var(--well);
		color: var(--ink);
	}
	.profile-status {
		display: flex;
		align-items: center;
		gap: 7px;
		margin: 13px 0;
		color: var(--muted);
		font-size: 12px;
	}
	.profile-status > span {
		width: 9px;
		height: 9px;
		border-radius: 50%;
		background: #858b91;
	}
	.profile-status.online > span {
		background: #43b581;
	}
	.profile-status small {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.profile-section {
		padding: 12px 0;
		border-top: 1px solid var(--line);
	}
	.profile-section h3 {
		margin: 0 0 8px;
		color: var(--muted);
		font-size: 10px;
		font-weight: 750;
		letter-spacing: 0.08em;
		text-transform: uppercase;
	}
	.profile-section p {
		margin: 0;
		color: var(--muted);
		font-size: 12px;
		line-height: 1.45;
	}
	.profile-details > div {
		display: flex;
		justify-content: space-between;
		gap: 10px;
		padding: 3px 0;
		font-size: 11px;
	}
	.profile-details > div span {
		color: var(--muted);
	}
	.profile-details > div strong {
		min-width: 0;
		overflow: hidden;
		text-align: right;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.profile-message {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 8px;
		width: 100%;
		margin-top: 8px;
		padding: 9px;
		border: 0;
		border-radius: 11px;
		background: var(--accent);
		color: white;
		font: inherit;
		font-size: 12px;
		font-weight: 700;
		cursor: pointer;
		transition:
			transform 140ms var(--ease-out),
			filter 140ms ease;
	}
	.profile-message:hover {
		filter: brightness(1.05);
		transform: translateY(-1px);
	}
	@media (prefers-reduced-motion: reduce) {
		.community-pop:popover-open,
		.member-profile-popover {
			animation: none;
		}
		.profile-message {
			transition: none;
		}
	}
	.community-pop button {
		display: flex;
		align-items: center;
		gap: 9px;
		width: 100%;
		min-height: 38px;
		padding: 8px 10px;
		border: 0;
		border-radius: 10px;
		background: transparent;
		color: var(--ink);
		text-align: left;
		font: inherit;
		font-size: 12px;
		overflow-wrap: anywhere;
	}
	.community-pop button:hover,
	.community-pop button:focus-visible {
		background: var(--well);
	}
	.community-selector {
		display: flex;
		align-items: center;
		flex: 1;
		gap: 10px;
		min-width: 0;
		padding: 7px;
		border: 0;
		border-radius: 13px;
		background: transparent;
		color: var(--ink);
		text-align: left;
		font: inherit;
		cursor: pointer;
		transition: background-color 150ms ease;
	}
	.community-selector:hover,
	.community-selector:focus-visible {
		background: var(--well);
	}
	.community-selector .community-header-text {
		flex: 1;
	}
	.community-selector-chevron {
		color: var(--muted);
	}
	.community-selector:active {
		transform: scale(0.99);
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
		grid-template-columns: minmax(0, 1fr);
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
		position: relative;
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
		padding: 0;
		border: 0;
		cursor: pointer;
	}
	.member-info {
		min-width: 0;
		flex: 1;
	}
	.member-info .member-profile-trigger {
		display: block;
		font-size: 13px;
		color: var(--sb-text);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.member-info .member-profile-trigger {
		width: 100%;
		padding: 0;
		border: 0;
		background: transparent;
		text-align: left;
		font: inherit;
		font-size: 13px;
		font-weight: 650;
		cursor: pointer;
	}
	.member-info .member-profile-trigger:hover {
		color: var(--accent-text);
		text-decoration: underline;
	}
	.member-avatar:focus-visible,
	.member-profile-trigger:focus-visible,
	.profile-author:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
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
	.channel-create-form {
		margin: 10px 2px 14px;
		padding: 13px;
		border: 1px solid var(--line);
		border-radius: 16px;
		background: var(--panel);
		box-shadow: 0 8px 22px rgb(30 32 26 / 6%);
		animation: chat-reveal 170ms var(--ease-out) both;
	}
	.channel-create-form::before {
		content: 'A new corner';
		display: block;
		margin-bottom: 10px;
		color: var(--ink);
		font-size: 13px;
		font-weight: 700;
		letter-spacing: -0.02em;
	}
	.channel-name-label {
		display: block;
		margin: 0 1px 5px;
		color: var(--muted);
		font-size: 10px;
		font-weight: 700;
		letter-spacing: 0.04em;
		text-transform: uppercase;
	}
	.channel-name-hint {
		margin: 6px 2px 12px;
		font-size: 11px;
		line-height: 1.45;
	}
	.channel-password-label {
		display: grid;
		gap: 6px;
		margin: 0 0 12px;
		color: var(--ink);
		font-size: 11px;
		font-weight: 650;
	}
	.channel-password-label small {
		color: var(--muted);
		font-weight: 450;
	}
	.rail-add-btn {
		width: 28px;
		height: 28px;
		border-radius: 9px;
	}
	.rail-add-btn:hover:not(:disabled) {
		background: var(--accent-lt);
		color: var(--accent-text);
	}
	.locked-chip {
		flex: none;
		padding: 2px 6px;
		border-radius: 999px;
		background: var(--well);
		color: var(--muted);
		font-size: 9px;
		font-weight: 650;
	}
	.channel-menu {
		position: fixed;
		top: 0;
		bottom: auto;
		right: auto;
		z-index: 40;
		min-width: 220px;
		max-height: calc(100dvh - 16px);
		margin: 0;
		padding: 7px;
		border: 1px solid var(--line);
		border-radius: 16px;
		background: var(--panel);
		box-shadow: 0 14px 38px rgb(30 32 26 / 17%);
		animation: chat-reveal 150ms var(--ease-out) both;
		transform-origin: top left;
		overflow-y: auto;
	}
	.channel-menu button {
		padding: 9px 10px;
		border-radius: 10px;
	}
	.channel-menu .menu-danger {
		margin-top: 4px;
		border-top: 1px solid var(--line);
	}
	.locked-channel {
		display: flex;
		flex: 1;
		min-height: 0;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		padding: 32px;
		text-align: center;
	}
	.locked-channel-icon {
		display: grid;
		place-items: center;
		width: 56px;
		height: 56px;
		margin-bottom: 16px;
		border: 1px solid var(--line);
		border-radius: 19px;
		background: var(--well);
		color: var(--accent-text);
	}
	.locked-eyebrow {
		margin: 0 0 8px !important;
		color: var(--accent-text) !important;
		font-size: 10px !important;
		font-weight: 750;
		letter-spacing: 0.12em;
		text-transform: uppercase;
	}
	.locked-channel h3 {
		margin: 0;
		color: var(--ink);
		font-size: clamp(24px, 3vw, 34px);
		letter-spacing: -0.05em;
	}
	.locked-channel > p:not(.locked-eyebrow) {
		max-width: 36ch;
		margin: 9px 0 20px;
		color: var(--muted);
		line-height: 1.6;
	}
	.locked-channel form {
		display: flex;
		width: min(380px, 100%);
		gap: 8px;
	}
	.unlock-button {
		flex: none;
		padding: 0 16px;
		border: 0;
		border-radius: 12px;
		background: var(--accent);
		color: white;
		font: inherit;
		font-size: 12px;
		font-weight: 700;
	}
	.unlock-button:hover:not(:disabled) {
		background: var(--accent-h);
	}
	.account-menu {
		padding: 10px;
	}
	.workspace-scrim {
		position: absolute;
		inset: 0;
		z-index: 10;
		border: 0;
		border-radius: inherit;
		background: rgb(28 30 26 / 24%);
		backdrop-filter: blur(2px);
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
	}
</style>
