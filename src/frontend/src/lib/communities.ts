/** Browser contract for the public community API. */
import { session } from './session.svelte';

export type Community = {
	id: number;
	name: string;
	description: string;
	school: string;
	course: string;
	owner_id: string | number | null;
	member_count: number;
	role: 'visitor' | 'member' | 'moderator' | 'owner';
	channels?: Channel[];
};

export type Channel = {
	id: number;
	name: string;
	position: number;
	private?: boolean;
	read_only?: boolean;
	slowmode_seconds?: number;
	topic?: string;
	archived: boolean;
};
export type Message = {
	id: number;
	channel_id: number;
	author_name: string;
	content: string;
	poll?: Poll | null;
	file_name?: string;
	reply_to: number | null;
	created_at: string;
	edited_at: string | null;
	deleted_at: string | null;
	pinned_at: string | null;
	reactions: { emoji: string; count: number; me: boolean }[];
	mine: boolean;
	can_delete: boolean;
};
export type Member = {
	user_id: string;
	display_name: string;
	is_me: boolean;
	role: 'member' | 'moderator';
	joined_at: string;
};
export type GuestMember = {
	id: number;
	display_name: string;
	is_me: boolean;
	role: 'owner' | 'member';
};
export type Invite = {
	id: number;
	created_at: string;
	expires_at: string | null;
	max_uses: number | null;
	uses: number;
	revoked: boolean;
};
export type DirectConversation = { id: number; other_name: string; updated_at: string };
export type DirectMessage = {
	reactions?: Message['reactions'];
	pinned_at?: string | null;
	id: number;
	author_name: string;
	content: string;
	poll?: Poll | null;
	file_name?: string;
	reply_to: number | null;
	created_at: string;
	edited_at: string | null;
	deleted_at: string | null;
	mine: boolean;
};

function csrfToken(): string {
	return (
		document.cookie
			.split('; ')
			.find((part) => part.startsWith('csrftoken='))
			?.split('=')[1] ?? ''
	);
}

export async function communityRequest<T>(path: string, method = 'GET', body?: object): Promise<T> {
	const credentials = await session.communityCredentials();
	const response = await fetch(`/api${path}`, {
		method,
		credentials: 'same-origin',
		headers: {
			accept: 'application/json',
			...(credentials ? { authorization: `Bearer ${credentials.access}` } : {}),
			...(credentials?.id ? { 'x-id-token': credentials.id } : {}),
			...(body && !(body instanceof FormData) ? { 'content-type': 'application/json' } : {}),
			...(method !== 'GET' ? { 'x-csrftoken': csrfToken() } : {})
		},
		...(body ? { body: body instanceof FormData ? body : JSON.stringify(body) } : {})
	});
	if (!response.ok) {
		const result = await response.json().catch(() => null);
		if (
			response.status === 401 ||
			(response.status === 403 && result?.error?.code === 'unauthorized')
		) {
			throw new Error('Sign in to your StudySpot account to continue.');
		}
		throw new Error(result?.error?.message ?? `Request failed (${response.status}).`);
	}
	return response.status === 204 ? (undefined as T) : await response.json();
}

export function composeMessage(
	body: { content: string; reply_to?: number },
	file: File | undefined
) {
	if (!file) return body;
	const form = new FormData();
	for (const [key, value] of Object.entries(body)) form.set(key, String(value));
	form.set('file', file);
	return form;
}

export type Poll = { options: string[]; counts: number[]; mine: number | null };
