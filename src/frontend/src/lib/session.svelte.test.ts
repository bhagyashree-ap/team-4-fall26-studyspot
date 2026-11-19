/**
 * The session's decisions, with Auth0 and the API both stood in for.
 *
 * Run in the browser project because the module holds runes state, which only
 * compiles in a `.svelte.ts` file.
 */

import { describe, expect, it } from 'vitest';
import type { Account } from './contract';
import { Session, safeReturnTo, type AuthClient, type PendingStore } from './session.svelte';

const CONFIG = { enabled: true, domain: 'x.auth0.com', client_id: 'spa', audience: 'api' };
const TOKEN = `header.${btoa(JSON.stringify({ sub: 'auth0|ada' }))}.signature`;

const ACCOUNT: Account = {
	email: 'ada@nyu.edu',
	email_verified: true,
	username: 'ada',
	account_type: 'student',
	business_name: '',
	created_at: '2026-10-27T12:00:00Z'
};

function json(body: unknown, status = 200): Response {
	return new Response(JSON.stringify(body), {
		status,
		headers: { 'content-type': 'application/json' }
	});
}

type Options = {
	enabled?: boolean;
	authenticated?: boolean;
	account?: Account;
	returnTo?: string;
	storage?: PendingStore | null;
	/** Answers `POST /account`; by default it accepts the choice. */
	onPost?: (body: unknown) => Response;
};

/** An in-memory stand-in for localStorage. */
function memoryStorage(): PendingStore & { items: Map<string, string> } {
	const items = new Map<string, string>();
	return {
		items,
		getItem: (key) => items.get(key) ?? null,
		setItem: (key, value) => void items.set(key, value),
		removeItem: (key) => void items.delete(key)
	};
}

/** A session wired to a fake client, and a log of what was asked of the client. */
function setup({
	enabled = true,
	authenticated = true,
	account = ACCOUNT,
	returnTo,
	storage = null,
	onPost
}: Options = {}) {
	const posted: unknown[] = [];
	const log: { method: string; argument?: unknown }[] = [];

	const client = {
		checkSession: async () => void log.push({ method: 'checkSession' }),
		isAuthenticated: async () => authenticated,
		getTokenSilently: async (argument?: unknown) => {
			log.push({ method: 'getTokenSilently', argument });
			return TOKEN;
		},
		getIdTokenClaims: async () => ({ __raw: 'id-token' }),
		loginWithRedirect: async (argument?: unknown) =>
			void log.push({ method: 'loginWithRedirect', argument }),
		handleRedirectCallback: async () => ({ appState: { returnTo } }),
		logout: async (argument?: unknown) => void log.push({ method: 'logout', argument })
	} as unknown as AuthClient;

	const fetcher = (async (input: RequestInfo | URL, init: RequestInit = {}) => {
		if (String(input) === '/api/auth/config') return json(enabled ? CONFIG : { enabled: false });
		if (init.method === 'POST') {
			const body = JSON.parse(String(init.body));
			posted.push(body);
			return onPost ? onPost(body) : json({ ...account, ...body }, 201);
		}
		return json(account);
	}) as typeof globalThis.fetch;

	const session = new Session({ fetcher, createClient: async () => client, storage });
	return { session, log, posted };
}

describe('start', () => {
	it('is disabled when the API has no Auth0 tenant', async () => {
		const { session, log } = setup({ enabled: false });

		await session.start();

		expect(session.status).toBe('disabled');
		expect(session.communityCredentials()).toBeNull();
		expect(log).toEqual([]);
	});

	it('is signed out without an Auth0 session', async () => {
		const { session } = setup({ authenticated: false });

		await session.start();

		expect(session.status).toBe('signed-out');
		expect(session.account).toBeNull();
	});

	it('loads the account of whoever is logged in', async () => {
		const { session } = setup();

		await session.start();

		expect(session.status).toBe('signed-in');
		expect(session.account).toEqual(ACCOUNT);
		expect(await session.communityCredentials()).toEqual({ access: TOKEN, id: 'id-token' });
	});

	it('only starts once', async () => {
		const { session, log } = setup();

		await Promise.all([session.start(), session.start()]);

		expect(log.filter((entry) => entry.method === 'checkSession')).toHaveLength(1);
	});

	it('leaves the callback page to finish the log-in', async () => {
		const { session, log } = setup();

		await session.start({ callback: true });

		expect(session.status).toBe('loading');
		expect(log).toEqual([]);
	});
});

describe('finishLogIn', () => {
	it('sends a new account to choose its type', async () => {
		const { session } = setup({ account: { ...ACCOUNT, account_type: null }, returnTo: '/spots' });

		expect(await session.finishLogIn()).toBe('/account');
	});

	it('returns an existing account to where it started', async () => {
		const { session } = setup({ returnTo: '/spots/facdb:bobst' });

		expect(await session.finishLogIn()).toBe('/spots/facdb:bobst');
		expect(session.status).toBe('signed-in');
	});

	it('says why Auth0 refused, in Auth0’s words', async () => {
		// What Auth0 really answered while the tenant had no API configured.
		const session = new Session({
			fetcher: (async () => json(CONFIG)) as typeof globalThis.fetch,
			createClient: async () =>
				({
					handleRedirectCallback: async () => {
						throw Object.assign(new Error('access_denied'), {
							error: 'access_denied',
							error_description: 'Service not found: https://api.studyspot.app'
						});
					}
				}) as unknown as AuthClient,
			storage: null
		});

		await session.finishLogIn();

		expect(session.status).toBe('error');
		expect(session.error).toBe(
			'Auth0 could not log you in: Service not found: https://api.studyspot.app'
		);
	});

	it('will not return to another site', async () => {
		const { session } = setup({ returnTo: '//evil.example/phish' });

		expect(await session.finishLogIn()).toBe('/');
	});
});

describe('redirects', () => {
	it('logs in, coming back to the page it left', async () => {
		const { session, log } = setup({ authenticated: false });

		await session.logIn('/spots/facdb:bobst');

		expect(log.at(-1)).toEqual({
			method: 'loginWithRedirect',
			argument: { appState: { returnTo: '/spots/facdb:bobst' }, authorizationParams: {} }
		});
	});

	it('opens sign-up rather than log-in', async () => {
		const { session, log } = setup({ authenticated: false });

		await session.signUp();

		expect(log.at(-1)).toMatchObject({
			argument: { authorizationParams: { screen_hint: 'signup' } }
		});
	});

	it('forgets the account on log-out', async () => {
		const { session, log } = setup();
		await session.start();

		await session.logOut();

		expect(session.status).toBe('signed-out');
		expect(session.account).toBeNull();
		expect(log.at(-1)?.method).toBe('logout');
	});
});

describe('refresh', () => {
	it('skips the token cache, so a newly verified email shows', async () => {
		const { session, log } = setup();
		await session.start();

		await session.refresh();

		expect(log.at(-1)).toEqual({ method: 'getTokenSilently', argument: { cacheMode: 'off' } });
	});
});

describe('safeReturnTo', () => {
	it('keeps paths on this site and nothing else', () => {
		expect(safeReturnTo('/account')).toBe('/account');
		expect(safeReturnTo('//evil.example')).toBe('/');
		expect(safeReturnTo('https://evil.example')).toBe('/');
		expect(safeReturnTo(undefined)).toBe('/');
	});
});

describe('the sign-up choice', () => {
	const NEW = { ...ACCOUNT, account_type: null };
	const CHOICE = { account_type: 'student', username: 'grace_h' } as const;

	it('is kept across the trip to Auth0', async () => {
		const storage = memoryStorage();
		const before = setup({ authenticated: false, storage });

		await before.session.signUp(CHOICE);

		// A new page load, as after Auth0 redirects back.
		const after = setup({ storage });
		expect(after.session.pending).toEqual(CHOICE);
		expect(before.log.at(-1)).toMatchObject({
			method: 'loginWithRedirect',
			argument: { authorizationParams: { screen_hint: 'signup' } }
		});
	});

	it('finishes sign-up by itself once the email is verified', async () => {
		const storage = memoryStorage();
		storage.setItem(
			'studyspot:pending-sign-up',
			JSON.stringify({ choice: CHOICE, subject: 'auth0|ada' })
		);
		const { session, posted } = setup({ account: NEW, storage });

		await session.start();

		expect(posted).toEqual([CHOICE]);
		expect(session.account?.account_type).toBe('student');
		expect(session.pending).toBeNull();
		expect(storage.getItem('studyspot:pending-sign-up')).toBeNull();
	});

	it('waits while the email is unverified', async () => {
		const storage = memoryStorage();
		storage.setItem(
			'studyspot:pending-sign-up',
			JSON.stringify({ choice: CHOICE, subject: 'auth0|ada' })
		);
		const { session, posted } = setup({ account: { ...NEW, email_verified: false }, storage });

		await session.start();

		expect(posted).toEqual([]);
		expect(session.pending).toEqual(CHOICE);
	});

	it('keeps the choice and the reason when the API refuses it', async () => {
		const storage = memoryStorage();
		storage.setItem(
			'studyspot:pending-sign-up',
			JSON.stringify({ choice: CHOICE, subject: 'auth0|ada' })
		);
		const { session } = setup({
			account: NEW,
			storage,
			onPost: () =>
				json(
					{
						error: {
							code: 'validation_error',
							message: 'The request could not be validated.',
							details: [
								{
									field: 'body.username',
									message: 'That username is taken.',
									type: 'username_taken'
								}
							]
						}
					},
					422
				)
		});

		await session.start();

		expect(session.status).toBe('signed-in');
		expect(session.pending).toEqual(CHOICE);
		expect(session.pendingError?.details[0].message).toBe('That username is taken.');
	});

	it('is forgotten on log-out', async () => {
		const storage = memoryStorage();
		storage.setItem(
			'studyspot:pending-sign-up',
			JSON.stringify({ choice: CHOICE, subject: 'auth0|ada' })
		);
		const { session } = setup({ account: { ...NEW, email_verified: false }, storage });
		await session.start();

		await session.logOut();

		expect(session.pending).toBeNull();
		expect(storage.getItem('studyspot:pending-sign-up')).toBeNull();
	});

	it('ignores anything in storage that is not a choice', () => {
		const storage = memoryStorage();
		storage.setItem('studyspot:pending-sign-up', '{"account_type":"admin"}');

		expect(setup({ storage }).session.pending).toBeNull();
	});
});
