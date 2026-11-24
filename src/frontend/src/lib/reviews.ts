import { authenticatedRequest, type Credentials } from './accounts';
import type { Fetcher } from './api';
import type { Review, ReviewDraft, ReviewReply, ReviewViewer } from './contract';

function collection(spotId: string): string {
	return `/api/spots/${encodeURIComponent(spotId)}/reviews`;
}

export function getReviewViewer(
	spotId: string,
	credentials: Credentials,
	fetcher?: Fetcher
): Promise<ReviewViewer> {
	return authenticatedRequest(`${collection(spotId)}/viewer`, credentials, {}, fetcher);
}

export function createReview(
	spotId: string,
	body: ReviewDraft,
	credentials: Credentials,
	fetcher?: Fetcher
): Promise<Review> {
	return authenticatedRequest(collection(spotId), credentials, { method: 'POST', body }, fetcher);
}

export function updateReview(
	spotId: string,
	body: ReviewDraft,
	credentials: Credentials,
	fetcher?: Fetcher
): Promise<Review> {
	return authenticatedRequest(
		`${collection(spotId)}/mine`,
		credentials,
		{ method: 'PATCH', body },
		fetcher
	);
}

export function deleteReview(
	spotId: string,
	credentials: Credentials,
	fetcher?: Fetcher
): Promise<void> {
	return authenticatedRequest(
		`${collection(spotId)}/mine`,
		credentials,
		{ method: 'DELETE' },
		fetcher
	);
}

export function putReviewReply(
	spotId: string,
	reviewId: number,
	body: string,
	credentials: Credentials,
	fetcher?: Fetcher
): Promise<ReviewReply> {
	return authenticatedRequest(
		`${collection(spotId)}/${reviewId}/reply`,
		credentials,
		{ method: 'PUT', body: { body } },
		fetcher
	);
}

export function deleteReviewReply(
	spotId: string,
	reviewId: number,
	credentials: Credentials,
	fetcher?: Fetcher
): Promise<void> {
	return authenticatedRequest(
		`${collection(spotId)}/${reviewId}/reply`,
		credentials,
		{ method: 'DELETE' },
		fetcher
	);
}
