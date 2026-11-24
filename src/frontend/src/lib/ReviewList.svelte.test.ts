import { page } from 'vitest/browser';
import { describe, expect, it } from 'vitest';
import { render } from 'vitest-browser-svelte';

import ReviewList from './ReviewList.svelte';
import type { Fetcher } from './api';
import type { Review, ReviewPage } from './contract';

const SPOT_ID = 'facdb:bobst';

function review(overrides: Partial<Review> = {}): Review {
	return {
		id: 1,
		spot: SPOT_ID,
		author: { username: 'ada' },
		rating: 4,
		noise: null,
		wifi: null,
		seating: null,
		outlets: null,
		body: '',
		// Midday UTC, so the date reads the same in every test machine's timezone.
		created_at: '2026-11-18T12:00:00Z',
		updated_at: '2026-11-18T12:00:00Z',
		...overrides
	};
}

function reviewPage(items: Review[]): ReviewPage {
	return {
		items,
		pagination: {
			limit: 20,
			offset: 0,
			count: items.length,
			total: items.length,
			has_more: false
		}
	};
}

function json(body: unknown, status = 200): Response {
	return new Response(JSON.stringify(body), {
		status,
		headers: { 'content-type': 'application/json' }
	});
}

/** Records every URL it is called with, and replies from a queue. */
function recorder(...replies: Array<(url: string) => Response | Promise<Response>>) {
	const urls: string[] = [];
	const fetcher = async (input: RequestInfo | URL) => {
		const url = String(input);
		urls.push(url);
		const reply = replies[Math.min(urls.length - 1, replies.length - 1)];
		return reply(url);
	};
	return { urls, fetcher: fetcher as unknown as Fetcher };
}

describe('the review list', () => {
	it('shows each review with its author, date, scores and comment', async () => {
		const { urls, fetcher } = recorder(() =>
			json(
				reviewPage([
					review({ id: 2, noise: 5, outlets: 2, body: 'Quiet upstairs, few outlets.' }),
					review({ id: 1, author: { username: null }, rating: 3 })
				])
			)
		);

		render(ReviewList, { spotId: SPOT_ID, fetcher });

		await expect.element(page.getByText('Quiet upstairs, few outlets.')).toBeInTheDocument();
		await expect.element(page.getByText('ada')).toBeInTheDocument();
		await expect.element(page.getByText('A student')).toBeInTheDocument();
		await expect.element(page.getByText('Overall 4/5')).toBeInTheDocument();
		await expect.element(page.getByText('Overall 3/5')).toBeInTheDocument();
		await expect.element(page.getByText('Quiet 5/5 · Outlets 2/5')).toBeInTheDocument();
		await expect.element(page.getByText('5 is best')).toBeInTheDocument();
		expect(page.getByText('Nov 18, 2026').elements()).toHaveLength(2);
		// A score the author left out is not shown at all.
		await expect.element(page.getByText(/Wi-Fi|Seating/)).not.toBeInTheDocument();
		expect(urls).toEqual([`/api/spots/${encodeURIComponent(SPOT_ID)}/reviews?limit=20&offset=0`]);
	});

	it('says so when the spot has no reviews', async () => {
		const { fetcher } = recorder(() => json(reviewPage([])));

		render(ReviewList, { spotId: SPOT_ID, fetcher });

		await expect.element(page.getByText('No reviews yet.')).toBeInTheDocument();
	});

	it('shows that it is loading until the reply arrives', async () => {
		let reply: (response: Response) => void = () => {};
		const { fetcher } = recorder(() => new Promise<Response>((resolve) => (reply = resolve)));

		render(ReviewList, { spotId: SPOT_ID, fetcher });

		await expect.element(page.getByText('Loading reviews…')).toBeInTheDocument();
		reply(json(reviewPage([])));
		await expect.element(page.getByText('No reviews yet.')).toBeInTheDocument();
		await expect.element(page.getByText('Loading reviews…')).not.toBeInTheDocument();
	});

	it('reports a failed request and loads again on retry', async () => {
		const { urls, fetcher } = recorder(
			() => json({ error: { code: 'internal_error', message: 'Down.', details: [] } }, 500),
			() => json(reviewPage([review({ body: 'Worth the wait.' })]))
		);

		render(ReviewList, { spotId: SPOT_ID, fetcher });

		await expect.element(page.getByRole('alert')).toHaveTextContent('Could not load reviews.');
		await page.getByRole('button', { name: 'Try again' }).click();

		await expect.element(page.getByText('Worth the wait.')).toBeInTheDocument();
		await expect.element(page.getByRole('alert')).not.toBeInTheDocument();
		expect(urls).toHaveLength(2);
	});

	it('never shows a slow reply for the previous spot after switching', async () => {
		let replyForFirst: (response: Response) => void = () => {};
		const { fetcher } = recorder(
			() => new Promise<Response>((resolve) => (replyForFirst = resolve)),
			() => json(reviewPage([review({ id: 2, spot: 'facdb:other', body: 'The current spot.' })]))
		);

		const view = await render(ReviewList, { spotId: SPOT_ID, fetcher });
		await view.rerender({ spotId: 'facdb:other' });
		await expect.element(page.getByText('The current spot.')).toBeInTheDocument();

		replyForFirst(json(reviewPage([review({ body: 'The previous spot.' })])));

		// Give the stale reply every chance to land before checking it did not.
		await new Promise((resolve) => setTimeout(resolve, 50));
		await expect.element(page.getByText('The previous spot.')).not.toBeInTheDocument();
		await expect.element(page.getByText('The current spot.')).toBeInTheDocument();
	});
});
