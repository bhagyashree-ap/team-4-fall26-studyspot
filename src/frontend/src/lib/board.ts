import { resolve } from '$app/paths';
import type { ResolvedPathname } from '$app/types';
import { communityRequest } from './communities';

export type PostKind = 'question' | 'information' | 'announcement';
export type TagKind = 'subject' | 'university' | 'spot';
export type TagValue = { kind: TagKind; value: string };
export type TagView = TagValue & { label: string; available: boolean };
export type TagSuggestion = TagView & { post_count: number };
export type BoardAuthor = { kind: 'guest' | 'student' | 'business'; name: string };
export type BoardPost = {
	id: number;
	kind: PostKind;
	title: string;
	body: string;
	tags: TagView[];
	author: BoardAuthor;
	created_at: string;
	updated_at: string;
	comment_count: number;
	can_edit: boolean;
	can_delete: boolean;
	can_report: boolean;
};
export type BoardComment = {
	id: number;
	post_id: number;
	body: string;
	author: BoardAuthor;
	created_at: string;
	updated_at: string;
	can_edit: boolean;
	can_delete: boolean;
	can_report: boolean;
};
export type PostDraft = { kind: PostKind; title: string; body: string; tags: TagValue[] };
export type BoardAccess = {
	viewer: 'visitor' | 'guest' | 'student' | 'business' | 'unfinished' | 'inactive';
	guest_access: boolean;
	create_kinds: PostKind[];
	can_comment: boolean;
	can_report: boolean;
	limits: { title: number; body: number; comment: number; reason: number };
};
export type BoardPage<T> = { items: T[]; has_more: boolean };
export type BoardFilters = {
	q: string;
	subject: string;
	university: string;
	spot: string;
	kind: string;
};
export const kindLabels: Record<PostKind, string> = {
	question: 'Question',
	information: 'Information',
	announcement: 'Announcement'
};
export const tagLabels: Record<TagKind, string> = {
	subject: 'Subject',
	university: 'University',
	spot: 'Study spot'
};

export function boardFilters(url: URL): BoardFilters {
	return {
		q: url.searchParams.get('q') ?? '',
		subject: url.searchParams.get('subject') ?? '',
		university: url.searchParams.get('university') ?? '',
		spot: url.searchParams.get('spot') ?? '',
		kind: url.searchParams.get('kind') ?? ''
	};
}

function filterParams(filters: Partial<BoardFilters>): URLSearchParams {
	const params = new URLSearchParams();
	for (const [key, value] of Object.entries(filters)) {
		if (value?.trim()) params.set(key, value.trim());
	}
	return params;
}

export function boardUrl(
	filters: Partial<BoardFilters> = {},
	detail?: number | 'compose'
): ResolvedPathname {
	const params = filterParams(filters);
	if (detail === 'compose') params.set('compose', '1');
	else if (detail !== undefined) params.set('post', String(detail));
	const query = params.toString();
	return query ? resolve(`/board?${query}`) : resolve('/board');
}

export const fetchBoardAccess = () => communityRequest<BoardAccess>('/board/access');
export function fetchBoardPosts(filters: Partial<BoardFilters>, before?: number) {
	const params = filterParams(filters);
	if (before !== undefined) params.set('before', String(before));
	return communityRequest<BoardPage<BoardPost>>(`/board/posts?${params}`);
}
export const fetchBoardPost = (id: number) => communityRequest<BoardPost>(`/board/posts/${id}`);
export const createBoardPost = (draft: PostDraft) =>
	communityRequest<BoardPost>('/board/posts', 'POST', draft);
export const updateBoardPost = (id: number, draft: Partial<PostDraft>) =>
	communityRequest<BoardPost>(`/board/posts/${id}`, 'PATCH', draft);
export const deleteBoardPost = (id: number) =>
	communityRequest<void>(`/board/posts/${id}`, 'DELETE');
export function fetchBoardComments(post: number, after?: number) {
	const params = new URLSearchParams();
	if (after !== undefined) params.set('after', String(after));
	return communityRequest<BoardPage<BoardComment>>(`/board/posts/${post}/comments?${params}`);
}
export const createBoardComment = (post: number, body: string) =>
	communityRequest<BoardComment>(`/board/posts/${post}/comments`, 'POST', { body });
export const updateBoardComment = (id: number, body: string) =>
	communityRequest<BoardComment>(`/board/comments/${id}`, 'PATCH', { body });
export const deleteBoardComment = (id: number) =>
	communityRequest<void>(`/board/comments/${id}`, 'DELETE');
export const fetchBoardTags = (kind: TagKind, q: string) =>
	communityRequest<{ items: TagSuggestion[] }>(
		`/board/tags?${new URLSearchParams({ kind, q, limit: '10' })}`
	);
export const reportBoardPost = (id: number, reason: string) =>
	communityRequest<{ reported: true }>(`/board/posts/${id}/reports`, 'POST', { reason });
export const reportBoardComment = (id: number, reason: string) =>
	communityRequest<{ reported: true }>(`/board/comments/${id}/reports`, 'POST', { reason });

export function boardError(error: unknown): string {
	return error instanceof Error ? error.message : 'The request failed. Please try again.';
}

export function boardDate(value: string): string {
	return new Date(value).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
}
