import { communityRequest } from './communities';

export const mergeMessages = <T extends { id: number }>(messages: T[], updates: T[]) =>
	Array.from(new Map([...messages, ...updates].map((m) => [m.id, m])).values()).sort(
		(a, b) => a.id - b.id
	);

export async function pollMessages<T extends { id: number }>(
	url: string,
	after: number,
	visible: number[]
) {
	const page = await communityRequest<{ items: T[]; has_more: boolean }>(url + '?after=' + after);
	const snapshot = visible.length
		? await communityRequest<{ items: T[] }>(url + '/snapshot', 'POST', { ids: visible })
		: { items: [] };
	return {
		updates: mergeMessages(snapshot.items, page.items),
		after: page.items.at(-1)?.id ?? after,
		more: page.has_more
	};
}
