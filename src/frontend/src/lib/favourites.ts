import { ApiError, isErrorEnvelope, type Fetcher } from './api';
import type { Credentials } from './accounts';
import type { SpotPage } from './contract';

async function request(
	path: string,
	credentials: Credentials,
	method: 'GET' | 'PUT' | 'DELETE',
	fetcher: Fetcher
): Promise<Response> {
	const headers: Record<string, string> = {
		accept: 'application/json',
		authorization: `Bearer ${credentials.access}`
	};
	if (credentials.id) headers['x-id-token'] = credentials.id;
	let response: Response;
	try {
		response = await fetcher(path, { method, headers, cache: 'no-store' });
	} catch {
		throw new ApiError(
			'network_error',
			'Could not reach StudySpot. Check your connection and try again.',
			0
		);
	}
	if (!response.ok) {
		let body: unknown;
		try {
			body = await response.json();
		} catch {
			body = null;
		}
		if (isErrorEnvelope(body)) {
			throw new ApiError(
				body.error.code,
				body.error.message,
				response.status,
				body.error.details ?? []
			);
		}
		throw new ApiError('error', `The API returned ${response.status}.`, response.status);
	}
	return response;
}

export async function listFavourites(
	credentials: Credentials,
	{
		limit = 100,
		offset = 0,
		fetcher = globalThis.fetch
	}: { limit?: number; offset?: number; fetcher?: Fetcher } = {}
): Promise<SpotPage> {
	const parameters = new URLSearchParams({ limit: String(limit), offset: String(offset) });
	const response = await request(`/api/favourites?${parameters}`, credentials, 'GET', fetcher);
	try {
		const page: SpotPage = await response.json();
		if (
			!Array.isArray(page.items) ||
			!page.pagination ||
			!Number.isInteger(page.pagination.offset) ||
			!Number.isInteger(page.pagination.count) ||
			page.pagination.offset !== offset ||
			page.pagination.count !== page.items.length ||
			typeof page.pagination.has_more !== 'boolean' ||
			(page.pagination.has_more && page.items.length === 0)
		)
			throw new Error('Invalid page');
		return page;
	} catch {
		throw new ApiError(
			'invalid_response',
			'StudySpot returned an invalid favourites list.',
			response.status
		);
	}
}

export async function setFavourite(
	credentials: Credentials,
	spotId: string,
	saved: boolean,
	fetcher: Fetcher = globalThis.fetch
): Promise<void> {
	const response = await request(
		`/api/favourites/${encodeURIComponent(spotId)}`,
		credentials,
		saved ? 'PUT' : 'DELETE',
		fetcher
	);
	if (response.status !== 204) {
		throw new ApiError(
			'invalid_response',
			'StudySpot did not confirm the change. Please try again.',
			response.status
		);
	}
}
