import { page } from 'vitest/browser';
import { describe, expect, it } from 'vitest';
import { render } from 'vitest-browser-svelte';
import { tick } from 'svelte';

import ReviewList from './ReviewList.svelte';
import type { Fetcher } from './api';
import type { Account, AccountType, Review, ReviewPage, ReviewReply } from './contract';
import { Session, type AuthClient } from './session.svelte';

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
		reply: null,
		// Midday UTC, so the date reads the same in every test machine's timezone.
		created_at: '2026-11-18T12:00:00Z',
		updated_at: '2026-11-18T12:00:00Z',
		...overrides
	};
}

function reviewPage(
	items: Review[],
	{
		total = items.length,
		offset = 0,
		average = items.length ? 4 : null,
		hasMore = false
	}: {
		total?: number;
		offset?: number;
		average?: number | null;
		hasMore?: boolean;
	} = {}
): ReviewPage {
	return {
		items,
		pagination: {
			limit: 20,
			offset,
			count: items.length,
			total,
			has_more: hasMore
		},
		summary: { average_rating: average }
	};
}

function json(body: unknown, status = 200): Response {
	return new Response(JSON.stringify(body), {
		status,
		headers: { 'content-type': 'application/json' }
	});
}

function delayedResponse() {
	const pending = Promise.withResolvers<Response>();
	return {
		promise: pending.promise,
		async finish(response: Response): Promise<void> {
			const parsed = Promise.withResolvers<void>();
			const parse = response.json.bind(response);
			response.json = async () => {
				const body = await parse();
				parsed.resolve();
				return body;
			};
			pending.resolve(response);
			await parsed.promise;
			await tick();
		}
	};
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
		const reply = Promise.withResolvers<Response>();
		const { fetcher } = recorder(() => reply.promise);

		render(ReviewList, { spotId: SPOT_ID, fetcher });

		await expect.element(page.getByText('Loading reviews…')).toBeInTheDocument();
		reply.resolve(json(reviewPage([])));
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
		const previous = delayedResponse();
		const { fetcher } = recorder(
			() => previous.promise,
			() => json(reviewPage([review({ id: 2, spot: 'facdb:other', body: 'The current spot.' })]))
		);

		const view = await render(ReviewList, { spotId: SPOT_ID, fetcher });
		await view.rerender({ spotId: 'facdb:other' });
		await expect.element(page.getByText('The current spot.')).toBeInTheDocument();

		await previous.finish(json(reviewPage([review({ body: 'The previous spot.' })])));
		await expect.element(page.getByText('The previous spot.')).not.toBeInTheDocument();
		await expect.element(page.getByText('The current spot.')).toBeInTheDocument();
	});
});

function routed(reply: (url: URL, init: RequestInit) => Response | Promise<Response>): {
	fetcher: Fetcher;
	requests: { url: string; init: RequestInit }[];
} {
	const requests: { url: string; init: RequestInit }[] = [];
	const fetcher = (async (input: RequestInfo | URL, init: RequestInit = {}) => {
		requests.push({ url: String(input), init });
		return reply(new URL(String(input), 'https://studyspot.test'), init);
	}) as Fetcher;
	return { fetcher, requests };
}

async function started(accountType: AccountType | null = 'student', signedIn = true) {
	const account: Account = {
		email: 'ada@nyu.edu',
		email_verified: true,
		username: 'ada',
		account_type: accountType,
		business_name: accountType === 'business' ? 'A study cafe' : '',
		created_at: '2026-11-18T12:00:00Z'
	};
	let credentialGate: Promise<void> | null = null;
	let credentialReturned: PromiseWithResolvers<void> | null = null;
	const client = {
		checkSession: async () => {},
		isAuthenticated: async () => signedIn,
		getTokenSilently: async () => {
			await credentialGate;
			credentialReturned?.resolve();
			return `header.${btoa(JSON.stringify({ sub: 'auth0|ada' }))}.signature`;
		},
		getIdTokenClaims: async () => ({ __raw: 'id-token' }),
		loginWithRedirect: async () => {},
		handleRedirectCallback: async () => ({}),
		logout: async () => {}
	} as unknown as AuthClient;
	const session = new Session({
		fetcher: (async (input: RequestInfo | URL) =>
			String(input) === '/api/auth/config'
				? json({ enabled: true, domain: 'x.auth0.com', client_id: 'spa', audience: 'api' })
				: json(account)) as Fetcher,
		createClient: async () => client,
		storage: null
	});
	await session.start();
	return {
		session,
		holdCredentials(gate: Promise<void>): Promise<void> {
			credentialGate = gate;
			credentialReturned = Promise.withResolvers<void>();
			return credentialReturned.promise;
		}
	};
}

function ownerReply(body: string): ReviewReply {
	return {
		body,
		created_at: '2026-11-19T12:00:00Z',
		updated_at: '2026-11-19T12:00:00Z'
	};
}

describe('review summaries and pagination', () => {
	it('uses the full average and total, and appends the next public page', async () => {
		const first = Array.from({ length: 20 }, (_, index) => review({ id: index + 2 }));
		const { fetcher, requests } = routed((url) =>
			json(
				url.searchParams.get('offset') === '20'
					? reviewPage([review({ id: 1, body: 'An older review.' })], {
							offset: 20,
							total: 21,
							average: 4.3
						})
					: reviewPage(first, { total: 21, average: 4.3, hasMore: true })
			)
		);
		render(ReviewList, { spotId: SPOT_ID, fetcher });

		await expect
			.element(page.getByRole('region', { name: 'Reviews', exact: true }))
			.toHaveAttribute('id', 'reviews');
		await expect.element(page.getByText('4.3 out of 5')).toBeInTheDocument();
		await expect.element(page.getByText('21 reviews')).toBeInTheDocument();
		await page.getByRole('button', { name: 'Show more' }).click();
		await expect.element(page.getByText('An older review.')).toBeInTheDocument();
		expect(page.getByRole('article').elements()).toHaveLength(21);
		await expect.element(page.getByRole('button', { name: 'Show more' })).not.toBeInTheDocument();
		expect(
			requests.map(({ url }) => new URL(url, 'https://studyspot.test').searchParams.get('offset'))
		).toEqual(['0', '20']);
		expect(requests.every(({ init }) => !new Headers(init.headers).has('authorization'))).toBe(
			true
		);
	});

	it('offers another attempt without losing reviews when Show more fails', async () => {
		let attempts = 0;
		const { fetcher } = routed((url) => {
			if (url.searchParams.get('offset') === '0')
				return json(reviewPage([review({ body: 'Already loaded.' })], { total: 2, hasMore: true }));
			attempts++;
			return attempts === 1
				? json({ error: { code: 'internal_error', message: 'Down.', details: [] } }, 500)
				: json(reviewPage([review({ id: 2, body: 'Loaded on retry.' })], { offset: 1, total: 2 }));
		});
		render(ReviewList, { spotId: SPOT_ID, fetcher });

		await page.getByRole('button', { name: 'Show more' }).click();
		await expect.element(page.getByRole('alert')).toBeInTheDocument();
		await expect.element(page.getByText('Already loaded.')).toBeInTheDocument();
		await page.getByRole('button', { name: 'Show more' }).click();
		await expect.element(page.getByText('Loaded on retry.')).toBeInTheDocument();
		await expect.element(page.getByText('Already loaded.')).toBeInTheDocument();
	});

	it('shows an owner reply to public readers', async () => {
		const { fetcher } = recorder(() =>
			json(reviewPage([review({ reply: ownerReply('The upstairs outlets are repaired.') })]))
		);
		render(ReviewList, { spotId: SPOT_ID, fetcher });

		await expect.element(page.getByText('Reply from the owner')).toBeInTheDocument();
		await expect.element(page.getByText('The upstairs outlets are repaired.')).toBeInTheDocument();
		await expect.element(page.getByRole('button', { name: 'Edit reply' })).not.toBeInTheDocument();
	});

	it('keeps public reviews available when private viewer loading fails', async () => {
		const { session } = await started();
		const { fetcher, requests } = routed((url) =>
			url.pathname.endsWith('/viewer')
				? json(
						{
							error: {
								code: 'internal_error',
								message: 'Private options unavailable.',
								details: []
							}
						},
						500
					)
				: json(
						reviewPage([review({ body: 'Public reviews still work.' })], {
							average: 3.7,
							total: 12
						})
					)
		);
		render(ReviewList, { spotId: SPOT_ID, fetcher, session });

		await expect.element(page.getByText('Public reviews still work.')).toBeInTheDocument();
		await expect.element(page.getByText('3.7 out of 5')).toBeInTheDocument();
		await expect.element(page.getByRole('alert')).toHaveTextContent('Private options unavailable.');
		await expect
			.element(page.getByRole('button', { name: 'Try again for your review' }))
			.toBeInTheDocument();
		const publicRequest = requests.find(({ url }) => !url.includes('/viewer'));
		expect(new Headers(publicRequest?.init.headers).has('authorization')).toBe(false);
		const privateRequest = requests.find(({ url }) => url.includes('/viewer'));
		expect(new Headers(privateRequest?.init.headers).get('authorization')).toMatch(/^Bearer /);
	});

	it('links a guest back to this spot after sign in', async () => {
		const { session } = await started('student', false);
		const { fetcher } = recorder(() => json(reviewPage([])));
		render(ReviewList, { spotId: 'listing:123', fetcher, session });

		await expect.element(page.getByText('No ratings yet')).toBeInTheDocument();
		await expect.element(page.getByText('No reviews yet.')).toBeInTheDocument();
		const signIn = page.getByRole('link', { name: 'Sign in to write a review' });
		await expect.element(signIn).toBeInTheDocument();
		const query = signIn.element().getAttribute('href')?.split('?')[1];
		expect(new URLSearchParams(query).get('returnTo')).toBe(
			'/spots/listing?id=listing%3A123#reviews'
		);
		await expect
			.element(page.getByRole('button', { name: 'Write a review' }))
			.not.toBeInTheDocument();
	});

	it('reads as unrated against an API that answers without a summary', async () => {
		// The API and the frontend are published as separate steps, so a build
		// can reach a browser before the API that sends `summary`. The reviews
		// themselves are still readable; only the average is unknown.
		const complete = reviewPage([review({ body: 'Quiet upstairs.' })]);
		const withoutSummary: unknown = {
			items: complete.items,
			pagination: complete.pagination
		};
		const { fetcher } = recorder(() => json(withoutSummary));

		render(ReviewList, { spotId: SPOT_ID, fetcher });

		await expect.element(page.getByText('No ratings yet')).toBeInTheDocument();
		await expect.element(page.getByText('Quiet upstairs.')).toBeInTheDocument();
		await expect.element(page.getByText('1 review')).toBeInTheDocument();
	});
});

describe('a student managing their review', () => {
	it('reaches and edits an own review outside the first page, without duplicating it on Show more', async () => {
		const { session } = await started();
		let own = review({ id: 90, body: 'My older review.', rating: 3, noise: 2, wifi: 3 });
		const publicReview = review({
			id: 91,
			author: { username: 'another-student' },
			body: 'A public review.'
		});
		const { fetcher, requests } = routed((url, init) => {
			if (url.pathname.endsWith('/viewer')) return json({ kind: 'student', own_review: own });
			if (init.method === 'PATCH') {
				own = { ...own, ...JSON.parse(String(init.body)) };
				return json(own);
			}
			return json(
				url.searchParams.get('offset') === '1'
					? reviewPage([own], { total: 2, offset: 1 })
					: reviewPage([publicReview], { total: 2, hasMore: true, average: own.rating })
			);
		});
		render(ReviewList, { spotId: SPOT_ID, fetcher, session });

		await expect.element(page.getByRole('heading', { name: 'Your review' })).toBeInTheDocument();
		await expect.element(page.getByText('My older review.')).toBeInTheDocument();
		await page.getByRole('button', { name: 'Show more' }).click();
		await expect.element(page.getByRole('button', { name: 'Show more' })).not.toBeInTheDocument();
		expect(page.getByText('My older review.').elements()).toHaveLength(1);
		await page.getByRole('button', { name: 'Edit review' }).click();
		await expect.element(page.getByLabelText('Overall rating', { exact: true })).toHaveValue('3');
		await expect.element(page.getByLabelText('Quiet', { exact: true })).toHaveValue('2');
		await page.getByLabelText('Overall rating', { exact: true }).selectOptions('5');
		await page.getByLabelText('Quiet', { exact: true }).selectOptions('4');
		await page.getByLabelText('Wi-Fi', { exact: true }).selectOptions('5');
		await page.getByLabelText('Seating', { exact: true }).selectOptions('3');
		await page.getByLabelText('Outlets', { exact: true }).selectOptions('2');
		await page.getByLabelText('Review text', { exact: true }).fill('My updated review.');
		await page.getByRole('button', { name: 'Save review' }).click();
		await expect.element(page.getByText('My updated review.')).toBeInTheDocument();
		await expect.element(page.getByText('My older review.')).not.toBeInTheDocument();
		await expect.element(page.getByText('5.0 out of 5')).toBeInTheDocument();
		expect(page.getByText('My updated review.').elements()).toHaveLength(1);
		const patch = requests.find(({ init }) => init.method === 'PATCH');
		expect(patch?.url).toBe(`/api/spots/${encodeURIComponent(SPOT_ID)}/reviews/mine`);
		expect(JSON.parse(String(patch?.init.body))).toEqual({
			rating: 5,
			noise: 4,
			wifi: 5,
			seating: 3,
			outlets: 2,
			body: 'My updated review.'
		});
	});

	it('posts a review only after an overall rating is chosen and reloads public totals', async () => {
		const { session } = await started();
		let own: Review | null = null;
		const { fetcher, requests } = routed((url, init) => {
			if (url.pathname.endsWith('/viewer')) return json({ kind: 'student', own_review: own });
			if (init.method === 'POST') {
				own = review({ ...JSON.parse(String(init.body)) });
				return json(own, 201);
			}
			return json(reviewPage(own ? [own] : [], { average: own?.rating ?? null }));
		});
		render(ReviewList, { spotId: SPOT_ID, fetcher, session });

		await page.getByRole('button', { name: 'Write a review' }).click();
		await page.getByLabelText('Review text', { exact: true }).fill('Good light for studying.');
		await page.getByRole('button', { name: 'Post review' }).click();
		expect(requests.filter(({ init }) => init.method === 'POST')).toHaveLength(0);
		await page.getByLabelText('Overall rating', { exact: true }).selectOptions('4');
		await page.getByRole('button', { name: 'Post review' }).click();
		await expect.element(page.getByText('Good light for studying.')).toBeInTheDocument();
		await expect.element(page.getByText('4.0 out of 5')).toBeInTheDocument();
		await expect.element(page.getByText('1 review', { exact: true })).toBeInTheDocument();
		expect(page.getByText('Good light for studying.').elements()).toHaveLength(1);
		expect(
			JSON.parse(String(requests.find(({ init }) => init.method === 'POST')?.init.body))
		).toEqual({
			rating: 4,
			noise: null,
			wifi: null,
			seating: null,
			outlets: null,
			body: 'Good light for studying.'
		});
	});

	it('preserves a failed draft so the student can retry', async () => {
		const { session } = await started();
		let attempts = 0;
		let own: Review | null = null;
		const { fetcher } = routed((url, init) => {
			if (url.pathname.endsWith('/viewer')) return json({ kind: 'student', own_review: own });
			if (init.method === 'POST') {
				attempts++;
				if (attempts === 1) throw new TypeError('Offline');
				own = review({ ...JSON.parse(String(init.body)) });
				return json(own, 201);
			}
			return json(reviewPage(own ? [own] : []));
		});
		render(ReviewList, { spotId: SPOT_ID, fetcher, session });

		await page.getByRole('button', { name: 'Write a review' }).click();
		await page.getByLabelText('Overall rating', { exact: true }).selectOptions('4');
		await page.getByLabelText('Review text', { exact: true }).fill('Keep this draft.');
		await page.getByRole('button', { name: 'Post review' }).click();
		await expect.element(page.getByRole('alert')).toBeInTheDocument();
		await expect
			.element(page.getByLabelText('Review text', { exact: true }))
			.toHaveValue('Keep this draft.');
		await page.getByRole('button', { name: 'Post review' }).click();
		await expect.element(page.getByText('Keep this draft.', { exact: true })).toBeInTheDocument();
		await expect.element(page.getByRole('alert')).not.toBeInTheDocument();
	});

	it('reconciles a duplicate POST with the viewer without posting again', async () => {
		const { session } = await started();
		let own: Review | null = null;
		const { fetcher, requests } = routed((url, init) => {
			if (url.pathname.endsWith('/viewer')) return json({ kind: 'student', own_review: own });
			if (init.method === 'POST') {
				own = review({ body: 'The review saved by another tab.' });
				return json(
					{
						error: {
							code: 'review_exists',
							message: 'You already reviewed this spot.',
							details: []
						}
					},
					409
				);
			}
			return json(reviewPage(own ? [own] : []));
		});
		render(ReviewList, { spotId: SPOT_ID, fetcher, session });

		await page.getByRole('button', { name: 'Write a review' }).click();
		await page.getByLabelText('Overall rating', { exact: true }).selectOptions('5');
		await page
			.getByLabelText('Review text', { exact: true })
			.fill('Do not automatically repost this.');
		await page.getByRole('button', { name: 'Post review' }).click();
		await expect.element(page.getByText('The review saved by another tab.')).toBeInTheDocument();
		await expect.element(page.getByRole('button', { name: 'Edit review' })).toBeInTheDocument();
		await expect.element(page.getByRole('button', { name: 'Post review' })).not.toBeInTheDocument();
		await expect.element(page.getByText('1 review', { exact: true })).toBeInTheDocument();
		expect(requests.filter(({ init }) => init.method === 'POST')).toHaveLength(1);
		expect(requests.filter(({ url }) => url.includes('/viewer'))).toHaveLength(2);
	});

	it('requires confirmation before deleting and permits writing again afterward', async () => {
		const { session } = await started();
		let own: Review | null = review({
			body: 'Remove my review.',
			reply: ownerReply('Thanks for visiting.')
		});
		const { fetcher, requests } = routed((url, init) => {
			if (url.pathname.endsWith('/viewer')) return json({ kind: 'student', own_review: own });
			if (init.method === 'DELETE') {
				own = null;
				return new Response(null, { status: 204 });
			}
			return json(reviewPage(own ? [own] : []));
		});
		render(ReviewList, { spotId: SPOT_ID, fetcher, session });

		await page.getByRole('button', { name: 'Delete review', exact: true }).click();
		expect(requests.filter(({ init }) => init.method === 'DELETE')).toHaveLength(0);
		await page.getByRole('button', { name: 'Cancel', exact: true }).click();
		await expect.element(page.getByText('Remove my review.')).toBeInTheDocument();
		await page.getByRole('button', { name: 'Delete review', exact: true }).click();
		await page.getByRole('button', { name: 'Confirm delete review', exact: true }).click();
		await expect.element(page.getByRole('button', { name: 'Write a review' })).toBeInTheDocument();
		await expect.element(page.getByText('No ratings yet')).toBeInTheDocument();
		await expect.element(page.getByText('No reviews yet.')).toBeInTheDocument();
		await expect.element(page.getByText('Thanks for visiting.')).not.toBeInTheDocument();
		expect(requests.find(({ init }) => init.method === 'DELETE')?.url).toBe(
			`/api/spots/${encodeURIComponent(SPOT_ID)}/reviews/mine`
		);
	});
});

describe('an owner replying to reviews', () => {
	it('keeps an older-page review reachable through reply creation, editing and deletion', async () => {
		const { session } = await started('business');
		const first = Array.from({ length: 20 }, (_, index) =>
			review({ id: index + 2, author: { username: `student-${index}` } })
		);
		let older = review({ id: 1, author: { username: 'older' }, body: 'An older-page review.' });
		const { fetcher, requests } = routed((url, init) => {
			if (url.pathname.endsWith('/viewer')) return json({ kind: 'owner' });
			if (init.method === 'PUT') {
				const reply = ownerReply(JSON.parse(String(init.body)).body);
				older = { ...older, reply };
				return json(reply, 201);
			}
			if (init.method === 'DELETE') {
				older = { ...older, reply: null };
				return new Response(null, { status: 204 });
			}
			return json(
				url.searchParams.get('offset') === '20'
					? reviewPage([older], { offset: 20, total: 21 })
					: reviewPage(first, { total: 21, hasMore: true })
			);
		});
		render(ReviewList, { spotId: SPOT_ID, fetcher, session });

		await page.getByRole('button', { name: 'Show more' }).click();
		const card = page.getByRole('article', { name: 'Review by older', exact: true });
		await card.getByRole('button', { name: 'Reply', exact: true }).click();
		await card.getByLabelText('Public reply', { exact: true }).fill('Thanks for your feedback.');
		await card.getByRole('button', { name: 'Post reply', exact: true }).click();
		await expect.element(card.getByText('Reply from the owner')).toBeInTheDocument();
		await expect.element(card.getByText('Thanks for your feedback.')).toBeInTheDocument();
		await card.getByRole('button', { name: 'Edit reply', exact: true }).click();
		await card.getByLabelText('Public reply', { exact: true }).fill('We added more outlets.');
		await card.getByRole('button', { name: 'Save reply', exact: true }).click();
		await expect.element(card.getByText('We added more outlets.')).toBeInTheDocument();
		await card.getByRole('button', { name: 'Delete reply', exact: true }).click();
		expect(requests.filter(({ init }) => init.method === 'DELETE')).toHaveLength(0);
		await card.getByRole('button', { name: 'Confirm delete reply', exact: true }).click();
		await expect
			.element(card.getByRole('button', { name: 'Reply', exact: true }))
			.toBeInTheDocument();
		await expect.element(card.getByText('Reply from the owner')).not.toBeInTheDocument();
		await expect.element(card.getByText('An older-page review.')).toBeInTheDocument();
		expect(
			requests.filter(({ url }) => !url.includes('/viewer') && !url.includes('/reply'))
		).toHaveLength(2);
		expect(requests.filter(({ init }) => init.method === 'PUT').map(({ url }) => url)).toEqual([
			`/api/spots/${encodeURIComponent(SPOT_ID)}/reviews/1/reply`,
			`/api/spots/${encodeURIComponent(SPOT_ID)}/reviews/1/reply`
		]);
	});

	it('does not let a pending public page overwrite a newer owner reply', async () => {
		const { session } = await started('business');
		const more = delayedResponse();
		const { fetcher } = routed((url, init) => {
			if (url.pathname.endsWith('/viewer')) return json({ kind: 'owner' });
			if (init.method === 'PUT') return json(ownerReply('The latest reply.'));
			if (url.searchParams.get('offset') === '1') return more.promise;
			return json(
				reviewPage([review({ body: 'A review to reply to.' })], { total: 2, hasMore: true })
			);
		});
		render(ReviewList, { spotId: SPOT_ID, fetcher, session });

		await page.getByRole('button', { name: 'Show more' }).click();
		await page.getByRole('button', { name: 'Reply', exact: true }).click();
		await page.getByLabelText('Public reply', { exact: true }).fill('The latest reply.');
		await page.getByRole('button', { name: 'Post reply', exact: true }).click();
		await expect.element(page.getByText('The latest reply.')).toBeInTheDocument();
		await more.finish(
			json(reviewPage([review({ body: 'A stale copy.' })], { offset: 1, total: 2 }))
		);
		await expect.element(page.getByText('The latest reply.')).toBeInTheDocument();
		await expect.element(page.getByText('A stale copy.')).not.toBeInTheDocument();
		await expect.element(page.getByRole('button', { name: 'Edit reply' })).toBeInTheDocument();
	});

	it('preserves a failed public reply for retry', async () => {
		const { session } = await started('business');
		let attempts = 0;
		const { fetcher } = routed((url, init) => {
			if (url.pathname.endsWith('/viewer')) return json({ kind: 'owner' });
			if (init.method === 'PUT') {
				attempts++;
				return attempts === 1
					? json(
							{ error: { code: 'internal_error', message: 'Could not publish.', details: [] } },
							500
						)
					: json(ownerReply(JSON.parse(String(init.body)).body));
			}
			return json(reviewPage([review()]));
		});
		render(ReviewList, { spotId: SPOT_ID, fetcher, session });

		await page.getByRole('button', { name: 'Reply', exact: true }).click();
		await page.getByLabelText('Public reply', { exact: true }).fill('Keep this public reply.');
		await page.getByRole('button', { name: 'Post reply', exact: true }).click();
		await expect.element(page.getByRole('alert')).toHaveTextContent('Could not publish.');
		await expect
			.element(page.getByLabelText('Public reply', { exact: true }))
			.toHaveValue('Keep this public reply.');
		await page.getByRole('button', { name: 'Post reply', exact: true }).click();
		await expect
			.element(page.getByText('Keep this public reply.', { exact: true }))
			.toBeInTheDocument();
	});
});

describe('review session and navigation boundaries', () => {
	it('clears a private draft on spot changes and ignores a previous-spot mutation result', async () => {
		const { session } = await started();
		const post = delayedResponse();
		const { fetcher, requests } = routed((url, init) => {
			if (url.pathname.endsWith('/viewer')) return json({ kind: 'student', own_review: null });
			if (init.method === 'POST') return post.promise;
			return json(reviewPage([]));
		});
		const view = await render(ReviewList, { spotId: SPOT_ID, fetcher, session });

		await page.getByRole('button', { name: 'Write a review' }).click();
		await page.getByLabelText('Overall rating', { exact: true }).selectOptions('5');
		await page
			.getByLabelText('Review text', { exact: true })
			.fill('A private draft for the previous spot.');
		await page.getByRole('button', { name: 'Post review' }).click();
		await expect.element(page.getByRole('button', { name: 'Post review' })).toBeDisabled();
		await expect.poll(() => requests.filter(({ init }) => init.method === 'POST').length).toBe(1);
		await view.rerender({ spotId: 'facdb:other' });
		await page.getByRole('button', { name: 'Write a review' }).click();
		await expect.element(page.getByLabelText('Review text', { exact: true })).toHaveValue('');
		await post.finish(json(review({ body: 'The obsolete saved review.' }), 201));
		await expect.element(page.getByText('The obsolete saved review.')).not.toBeInTheDocument();
		await expect.element(page.getByLabelText('Review text', { exact: true })).toHaveValue('');
		await expect.element(page.getByText('Review posted.')).not.toBeInTheDocument();
	});

	it('does not send a mutation when the session changes while credentials are pending', async () => {
		const { session, holdCredentials } = await started();
		const { fetcher, requests } = routed((url) =>
			url.pathname.endsWith('/viewer')
				? json({ kind: 'student', own_review: null })
				: json(reviewPage([]))
		);
		render(ReviewList, { spotId: SPOT_ID, fetcher, session });
		await page.getByRole('button', { name: 'Write a review' }).click();
		await page.getByLabelText('Overall rating', { exact: true }).selectOptions('5');
		await page
			.getByLabelText('Review text', { exact: true })
			.fill('Never send this after sign out.');
		const gate = Promise.withResolvers<void>();
		const returned = holdCredentials(gate.promise);
		await page.getByRole('button', { name: 'Post review' }).click();
		await expect.element(page.getByRole('button', { name: 'Post review' })).toBeDisabled();
		session.status = 'signed-out';
		session.subject = null;
		session.generation++;
		await expect
			.element(page.getByRole('link', { name: 'Sign in to write a review' }))
			.toBeInTheDocument();
		gate.resolve();
		await returned;
		await tick();
		expect(requests.filter(({ init }) => init.method === 'POST')).toHaveLength(0);
		await expect
			.element(page.getByLabelText('Review text', { exact: true }))
			.not.toBeInTheDocument();
	});

	it('does not restore an obsolete private viewer even when replacement sessions share scope values', async () => {
		const first = await started();
		const second = await started();
		const previous = delayedResponse();
		let privateLoads = 0;
		const { fetcher } = routed((url) => {
			if (!url.pathname.endsWith('/viewer'))
				return json(reviewPage([review({ id: 20, body: 'Always public.' })]));
			privateLoads++;
			return privateLoads === 1
				? previous.promise
				: json({ kind: 'student', own_review: review({ id: 2, body: 'The current own review.' }) });
		});
		const view = await render(ReviewList, { spotId: SPOT_ID, fetcher, session: first.session });
		await expect.element(page.getByText('Loading your review options…')).toBeInTheDocument();
		await expect.poll(() => privateLoads).toBe(1);
		await view.rerender({ session: second.session });
		await expect.element(page.getByText('The current own review.')).toBeInTheDocument();
		await previous.finish(
			json({ kind: 'student', own_review: review({ body: 'The obsolete own review.' }) })
		);
		await expect.element(page.getByText('The obsolete own review.')).not.toBeInTheDocument();
		await expect.element(page.getByText('The current own review.')).toBeInTheDocument();
		await expect.element(page.getByText('Always public.')).toBeInTheDocument();
	});

	it('clears private controls after a current API 401 without hiding public reviews', async () => {
		const { session } = await started();
		const { fetcher } = routed((url, init) => {
			if (url.pathname.endsWith('/viewer')) return json({ kind: 'student', own_review: null });
			if (init.method === 'POST')
				return json(
					{ error: { code: 'unauthorized', message: 'Sign in again.', details: [] } },
					401
				);
			return json(reviewPage([review({ id: 20, body: 'A public review remains.' })]));
		});
		render(ReviewList, { spotId: SPOT_ID, fetcher, session });
		await page.getByRole('button', { name: 'Write a review' }).click();
		await page.getByLabelText('Overall rating', { exact: true }).selectOptions('4');
		await page.getByLabelText('Review text', { exact: true }).fill('A private draft.');
		await page.getByRole('button', { name: 'Post review' }).click();
		await expect
			.element(page.getByRole('link', { name: 'Sign in to write a review' }))
			.toBeInTheDocument();
		await expect
			.element(page.getByLabelText('Review text', { exact: true }))
			.not.toBeInTheDocument();
		await expect.element(page.getByText('A public review remains.')).toBeInTheDocument();
	});
});
