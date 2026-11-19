import { describe, expect, it } from 'vitest';
import type { Account, StudySpot } from './contract';
import { Favourites } from './favourites.svelte';
import { Session, type AuthClient } from './session.svelte';

const ACCOUNT: Account = {
	email: 'ada@nyu.edu',
	email_verified: true,
	username: 'ada',
	account_type: 'student',
	business_name: '',
	created_at: '2026-10-27T12:00:00Z'
};
const SPOT: StudySpot = {
	id: 'facdb:bobst',
	name: 'Bobst Library',
	category: 'academic_library',
	address: null,
	neighborhood: null,
	borough: 'Manhattan',
	latitude: 40.7,
	longitude: -74,
	university: null,
	operator: null,
	free_public_wifi: false,
	no_purchase_needed: true,
	subway_station: null,
	subway_routes: null,
	subway_metres: null,
	subway_step_free: null,
	nearby_spots: 0,
	outdoor_seating: false,
	indoor_seating: null,
	venue_wifi: null,
	opening_hours: null
};

function json(body: unknown, status = 200): Response {
	return new Response(JSON.stringify(body), {
		status,
		headers: { 'content-type': 'application/json' }
	});
}
function page(items: StudySpot[], offset = 0, hasMore = false): Response {
	return json({
		items,
		pagination: { offset, limit: 100, count: items.length, total: items.length, has_more: hasMore }
	});
}
function deferred<T>() {
	return Promise.withResolvers<T>();
}
async function setup(
	answer: (method: string, url: string) => Promise<Response> | Response,
	accountAnswer: () => Promise<Response> | Response = () => json(ACCOUNT)
) {
	let subject: string | null = 'auth0|ada';
	const requests: string[] = [];
	const fetcher = (async (input: RequestInfo | URL, init: RequestInit = {}) => {
		const url = String(input);
		if (url === '/api/auth/config')
			return json({ enabled: true, domain: 'x.auth0.com', client_id: 'spa', audience: 'api' });
		if (url === '/api/account') return accountAnswer();
		requests.push(init.method ?? 'GET');
		return answer(init.method ?? 'GET', url);
	}) as typeof fetch;
	const client = {
		checkSession: async () => {},
		isAuthenticated: async () => true,
		getTokenSilently: async () => `header.${btoa(JSON.stringify({ sub: subject }))}.signature`,
		getIdTokenClaims: async () => undefined,
		logout: async () => {},
		handleRedirectCallback: async () => ({ appState: { returnTo: '/' } })
	} as unknown as AuthClient;
	const session = new Session({ fetcher, createClient: async () => client, storage: null });
	await session.start();
	const favourites = new Favourites(session, fetcher);
	return {
		session,
		favourites,
		requests,
		switchSubject: (next: string | null) => {
			subject = next;
		}
	};
}

describe('account-scoped favourites', () => {
	it('does not call a missing ID unsaved before every page is loaded', async () => {
		const next = deferred<Response>();
		const requested = deferred<void>();
		const { favourites } = await setup((_, url) => {
			if (url.includes('offset=0')) return page([{ ...SPOT, id: 'first' }], 0, true);
			requested.resolve();
			return next.promise;
		});
		const loading = favourites.load();
		await requested.promise;
		expect(favourites.saved(SPOT.id)).toBeUndefined();
		expect(favourites.items).toEqual([]);
		next.resolve(page([SPOT], 1));
		await loading;
		expect(favourites.saved(SPOT.id)).toBe(true);
		expect(favourites.saved('absent')).toBe(false);
	});

	it('excludes overlapping actions on one ID and waits for 204 before success', async () => {
		const mutation = deferred<Response>();
		const requested = deferred<void>();
		const { favourites, requests } = await setup((method) => {
			if (method === 'GET') return page([]);
			requested.resolve();
			return mutation.promise;
		});
		await favourites.load();
		const save = favourites.change(SPOT, true);
		await requested.promise;
		await favourites.change(SPOT, false);
		expect(favourites.saved(SPOT.id)).toBe(false);
		expect(requests.filter((method) => method !== 'GET')).toEqual(['PUT']);
		mutation.resolve(new Response(null, { status: 204 }));
		await save;
		expect(favourites.saved(SPOT.id)).toBe(true);
	});

	it('preserves confirmed state and the original failed action for retry', async () => {
		let attempts = 0;
		const { favourites } = await setup((method) => {
			if (method === 'GET') return page([SPOT]);
			return ++attempts === 1 ? json({}, 200) : new Response(null, { status: 204 });
		});
		await favourites.load();
		await favourites.change(SPOT, false);
		expect(favourites.saved(SPOT.id)).toBe(true);
		expect(favourites.action(SPOT.id)).toMatchObject({ desired: false, pending: false });
		expect(favourites.action(SPOT.id)?.error).not.toBe('');
		await favourites.change(SPOT, favourites.action(SPOT.id)!.desired);
		expect(favourites.saved(SPOT.id)).toBe(false);
		expect(favourites.action(SPOT.id)).toBeUndefined();
	});

	it('does not let an older collection read undo a confirmed removal', async () => {
		const refresh = deferred<Response>();
		let reads = 0;
		const { favourites } = await setup((method) =>
			method !== 'GET'
				? new Response(null, { status: 204 })
				: ++reads === 1
					? page([SPOT])
					: refresh.promise
		);
		await favourites.load();
		const loading = favourites.load({ refresh: true });
		await favourites.change(SPOT, false);
		refresh.resolve(page([SPOT]));
		await loading;
		expect(favourites.items).toEqual([]);
		expect(favourites.saved(SPOT.id)).toBe(false);
	});

	it('does not revive an older read after student eligibility is rejected', async () => {
		const oldRead = deferred<Response>();
		const oldReadRequested = deferred<void>();
		const profile = deferred<Response>();
		const profileRequested = deferred<void>();
		let reads = 0;
		let accounts = 0;
		const { favourites, session } = await setup(
			(method) => {
				if (method !== 'GET')
					return json(
						{ error: { code: 'conflict', message: 'Student account required', details: [] } },
						409
					);
				if (++reads === 1) return page([SPOT]);
				oldReadRequested.resolve();
				return oldRead.promise;
			},
			() => {
				if (++accounts === 1) return json(ACCOUNT);
				profileRequested.resolve();
				return profile.promise;
			}
		);
		await favourites.load();
		const loading = favourites.load({ refresh: true });
		await oldReadRequested.promise;
		await favourites.change(SPOT, false);
		await profileRequested.promise;
		expect(favourites.items).toEqual([]);
		expect(favourites.saved(SPOT.id)).toBeUndefined();
		oldRead.resolve(page([SPOT]));
		await loading;
		try {
			expect(favourites.items).toEqual([]);
			expect(favourites.saved(SPOT.id)).toBeUndefined();
		} finally {
			profile.resolve(json({ ...ACCOUNT, account_type: 'business', business_name: 'Business' }));
			await expect.poll(() => session.account?.account_type).toBe('business');
		}
	});

	it('does not publish an earlier action after another spot rejects student eligibility', async () => {
		const mutation = deferred<Response>();
		const requested = deferred<void>();
		const profile = deferred<Response>();
		const profileRequested = deferred<void>();
		let writes = 0;
		let accounts = 0;
		const { favourites, session } = await setup(
			(method) => {
				if (method === 'GET') return page([]);
				if (++writes === 1) {
					requested.resolve();
					return mutation.promise;
				}
				return json(
					{ error: { code: 'conflict', message: 'Student account required', details: [] } },
					409
				);
			},
			() => {
				if (++accounts === 1) return json(ACCOUNT);
				profileRequested.resolve();
				return profile.promise;
			}
		);
		await favourites.load();
		const saving = favourites.change(SPOT, true);
		await requested.promise;
		await favourites.change({ ...SPOT, id: 'facdb:second' }, true);
		await profileRequested.promise;
		mutation.resolve(new Response(null, { status: 204 }));
		await saving;
		try {
			expect(favourites.items).toEqual([]);
			expect(favourites.saved(SPOT.id)).toBeUndefined();
			expect(favourites.action(SPOT.id)).toBeUndefined();
		} finally {
			profile.resolve(json({ ...ACCOUNT, account_type: 'business', business_name: 'Business' }));
			await expect.poll(() => session.account?.account_type).toBe('business');
		}
	});

	it('ignores an old principal response with 401 after a new login', async () => {
		const oldRead = deferred<Response>();
		const requested = deferred<void>();
		let reads = 0;
		const { favourites, session, switchSubject } = await setup(() => {
			if (++reads === 1) return page([SPOT]);
			if (reads === 2) {
				requested.resolve();
				return oldRead.promise;
			}
			return page([]);
		});
		await favourites.load();
		const loading = favourites.load({ refresh: true });
		await requested.promise;
		await session.logOut();
		switchSubject('auth0|bea');
		await session.finishLogIn();
		await favourites.load();
		oldRead.resolve(
			json({ error: { code: 'unauthorized', message: 'Old token expired', details: [] } }, 401)
		);
		await loading;
		expect(session.status).toBe('signed-in');
		expect(session.subject).toBe('auth0|bea');
		expect(favourites.status).toBe('ready');
		expect(favourites.items).toEqual([]);
		expect(favourites.saved(SPOT.id)).toBe(false);
	});

	it.each(['load', 'remove'])(
		'ignores an obsolete %s 401 after eligibility recovery in the same login',
		async (operation) => {
			const oldReply = deferred<Response>();
			const requested = deferred<void>();
			const profileRequested = deferred<void>();
			let reads = 0;
			let writes = 0;
			let accounts = 0;
			const { favourites, session } = await setup(
				(method) => {
					if (method === 'GET') {
						if (++reads === 2 && operation === 'load') {
							requested.resolve();
							return oldReply.promise;
						}
						return page([SPOT]);
					}
					if (++writes === 1 && operation === 'remove') {
						requested.resolve();
						return oldReply.promise;
					}
					return json(
						{ error: { code: 'conflict', message: 'Student account required', details: [] } },
						409
					);
				},
				() => {
					if (++accounts > 1) profileRequested.resolve();
					return json(ACCOUNT);
				}
			);
			await favourites.load();
			const pending =
				operation === 'load' ? favourites.load({ refresh: true }) : favourites.change(SPOT, false);
			await requested.promise;
			await favourites.change({ ...SPOT, id: 'facdb:second' }, true);
			await profileRequested.promise;
			await favourites.load({ refresh: true });
			expect(favourites.status).toBe('ready');
			oldReply.resolve(
				json({ error: { code: 'unauthorized', message: 'Old token expired', details: [] } }, 401)
			);
			await pending;
			expect(session.status).toBe('signed-in');
			expect(favourites.status).toBe('ready');
			expect(favourites.saved(SPOT.id)).toBe(true);
		}
	);

	it.each(['load', 'remove'])(
		'clears private state after a refused %s request',
		async (operation) => {
			let refused = false;
			const { favourites, session } = await setup(() =>
				refused
					? json({ error: { code: 'unauthorized', message: 'Session expired' } }, 401)
					: page([SPOT])
			);
			await favourites.load();
			refused = true;
			if (operation === 'load') await favourites.load({ refresh: true });
			else await favourites.change(SPOT, false);
			expect(session.status).toBe('signed-out');
			expect(favourites.items).toEqual([]);
			expect(favourites.saved(SPOT.id)).toBeUndefined();
		}
	);

	it('cannot resurrect a saved spot when its response arrives after logout', async () => {
		const mutation = deferred<Response>();
		const requested = deferred<void>();
		const { favourites, session } = await setup((method) => {
			if (method === 'GET') return page([]);
			requested.resolve();
			return mutation.promise;
		});
		await favourites.load();
		const saving = favourites.change(SPOT, true);
		await requested.promise;
		await session.logOut();
		mutation.resolve(new Response(null, { status: 204 }));
		await saving;
		expect(favourites.items).toEqual([]);
		expect(favourites.action(SPOT.id)).toBeUndefined();
		expect(session.account).toBeNull();
	});

	it('keeps a new principal isolated from old reads and their cleanup', async () => {
		const oldRead = Promise.withResolvers<Response>();
		const oldRequested = Promise.withResolvers<void>();
		const mutation = Promise.withResolvers<Response>();
		const mutationRequested = Promise.withResolvers<void>();
		let reads = 0;
		const { favourites, session, switchSubject } = await setup((method) => {
			if (method !== 'GET') {
				mutationRequested.resolve();
				return mutation.promise;
			}
			if (++reads === 1) {
				oldRequested.resolve();
				return oldRead.promise;
			}
			return page([]);
		});
		const loadingOld = favourites.load();
		await oldRequested.promise;
		await session.logOut();
		switchSubject('auth0|grace');
		await session.finishLogIn();
		await favourites.load();
		const saving = favourites.change(SPOT, true);
		await mutationRequested.promise;
		oldRead.resolve(page([SPOT]));
		await loadingOld;
		expect(favourites.items).toEqual([]);
		expect(favourites.action(SPOT.id)?.pending).toBe(true);
		mutation.resolve(new Response(null, { status: 204 }));
		await saving;
		expect(session.scope?.subject).toBe('auth0|grace');
		expect(favourites.saved(SPOT.id)).toBe(true);
	});

	it.each(['auth0|grace', null])(
		'does not send a favourite request with a changed or missing subject %s',
		async (subject) => {
			const { favourites, session, requests, switchSubject } = await setup(() => page([SPOT]));
			await favourites.load();
			switchSubject(subject);
			await favourites.change(SPOT, false);
			expect(requests).toEqual(['GET']);
			expect(session.account).toBeNull();
			expect(favourites.items).toEqual([]);
		}
	);

	it('keeps failed collection loading distinct from an empty confirmed list', async () => {
		let reads = 0;
		const { favourites } = await setup(() =>
			++reads === 1 ? json({ error: { code: 'error', message: 'Unavailable' } }, 503) : page([])
		);
		await favourites.load();
		expect(favourites.status).toBe('error');
		expect(favourites.saved(SPOT.id)).toBeUndefined();
		await favourites.load();
		expect(favourites.status).toBe('ready');
		expect(favourites.saved(SPOT.id)).toBe(false);
	});
});
