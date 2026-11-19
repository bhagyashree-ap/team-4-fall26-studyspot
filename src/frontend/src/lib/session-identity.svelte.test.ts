import { describe, expect, it } from 'vitest';
import type { Account } from './contract';
import {
	IDENTITY_KEY,
	Session,
	safeReturnTo,
	type AuthClient,
	type PendingStore
} from './session.svelte';

const ACCOUNT: Account = {
	email: 'ada@nyu.edu',
	email_verified: true,
	username: 'ada',
	account_type: 'student',
	business_name: '',
	created_at: '2026-10-27T12:00:00Z'
};
function json(body: unknown): Response {
	return new Response(JSON.stringify(body), { headers: { 'content-type': 'application/json' } });
}
function storage(): PendingStore {
	const items = new Map<string, string>();
	return {
		getItem: (key) => items.get(key) ?? null,
		setItem: (key, value) => {
			items.set(key, value);
		},
		removeItem: (key) => {
			items.delete(key);
		}
	};
}
function setup({
	store = null,
	subject = 'auth0|ada',
	account = ACCOUNT,
	authenticated = true,
	returnTo = '/account',
	beforeConfig,
	beforeClient
}: {
	store?: PendingStore | null;
	subject?: string;
	account?: Account;
	authenticated?: boolean;
	returnTo?: string;
	beforeConfig?: Promise<void>;
	beforeClient?: Promise<void>;
} = {}) {
	let current = account;
	let token: Promise<string> | null = null;
	let accountResponse: Promise<Response> | null = null;
	let postResponse: Promise<Response> | null = null;
	const blockedAccount = Promise.withResolvers<void>();
	const blockedPost = Promise.withResolvers<void>();
	const configRequested = Promise.withResolvers<void>();
	const clientRequested = Promise.withResolvers<void>();
	let notify = () => {};
	const requests: string[] = [];
	const client = {
		checkSession: async () => {},
		isAuthenticated: async () => authenticated,
		getTokenSilently: async () =>
			token ?? `header.${btoa(JSON.stringify({ sub: subject }))}.signature`,
		getIdTokenClaims: async () => ({ __raw: 'id-token', sub: 'not-the-access-subject' }),
		loginWithRedirect: async () => {},
		handleRedirectCallback: async () => ({ appState: { returnTo } }),
		logout: async () => {}
	} as unknown as AuthClient;
	const fetcher = (async (input: RequestInfo | URL, init: RequestInit = {}) => {
		if (String(input) === '/api/auth/config') {
			configRequested.resolve();
			await beforeConfig;
			return json({ enabled: true, domain: 'x.auth0.com', client_id: 'spa', audience: 'api' });
		}
		requests.push(init.method ?? 'GET');
		if (init.method === 'POST') {
			if (postResponse) {
				blockedPost.resolve();
				return postResponse;
			}
			current = { ...current, ...JSON.parse(String(init.body)) };
		}
		if (accountResponse) blockedAccount.resolve();
		return accountResponse ? (await accountResponse).clone() : json(current);
	}) as typeof fetch;
	const session = new Session({
		fetcher,
		createClient: async () => {
			clientRequested.resolve();
			await beforeClient;
			return client;
		},
		storage: store,
		subscribeIdentity: (listener) => {
			notify = listener;
		}
	});
	return {
		session,
		requests,
		configRequested: configRequested.promise,
		clientRequested: clientRequested.promise,
		blockedAccount: blockedAccount.promise,
		blockedPost: blockedPost.promise,
		notify: () => notify(),
		setAccount: (next: Account) => {
			current = next;
		},
		setSubject: (next: string) => {
			subject = next;
		},
		deferAccount: (response: Promise<Response>) => {
			accountResponse = response;
		},
		deferPost: (response: Promise<Response>) => {
			postResponse = response;
		},
		deferToken: (response: Promise<string>) => {
			token = response;
		}
	};
}

describe('stable browser identity', () => {
	it.each(['config', 'client'])('reconciles a login during %s initialization', async (stage) => {
		const store = storage();
		const pause = Promise.withResolvers<void>();
		const fixture = setup({
			store,
			...(stage === 'config' ? { beforeConfig: pause.promise } : { beforeClient: pause.promise })
		});
		const starting = fixture.session.start();
		await (stage === 'config' ? fixture.configRequested : fixture.clientRequested);
		fixture.setSubject('auth0|grace');
		fixture.setAccount({ ...ACCOUNT, username: 'grace' });
		store.setItem(IDENTITY_KEY, JSON.stringify({ subject: 'auth0|grace', nonce: 'startup' }));
		fixture.notify();
		pause.resolve();
		await starting;
		expect(fixture.session.status).toBe('signed-in');
		expect(fixture.session.scope?.subject).toBe('auth0|grace');
	});

	it.each(['config', 'client'])(
		'keeps login usable after logout during %s initialization',
		async (stage) => {
			const store = storage();
			const pause = Promise.withResolvers<void>();
			const fixture = setup({
				store,
				...(stage === 'config' ? { beforeConfig: pause.promise } : { beforeClient: pause.promise }),
				returnTo: '/spots/facdb:bobst'
			});
			const starting = fixture.session.start();
			await (stage === 'config' ? fixture.configRequested : fixture.clientRequested);
			store.setItem(IDENTITY_KEY, JSON.stringify({ subject: null, nonce: 'startup-logout' }));
			fixture.notify();
			pause.resolve();
			await starting;
			expect(fixture.session.status).toBe('signed-out');
			expect(await fixture.session.finishLogIn()).toBe('/spots/facdb:bobst');
			expect(fixture.session.status).toBe('signed-in');
		}
	);

	it.each(['config', 'client'])(
		'retains a recoverable error after %s startup fails',
		async (stage) => {
			const store = storage();
			const pause = Promise.withResolvers<void>();
			const fixture = setup({
				store,
				...(stage === 'config' ? { beforeConfig: pause.promise } : { beforeClient: pause.promise })
			});
			const starting = fixture.session.start();
			await (stage === 'config' ? fixture.configRequested : fixture.clientRequested);
			pause.reject(new TypeError('Startup unavailable'));
			await starting;
			expect(fixture.session.status).toBe('error');
			store.setItem(
				IDENTITY_KEY,
				JSON.stringify({ subject: 'auth0|grace', nonce: 'after-failure' })
			);
			fixture.notify();
			expect(fixture.session.status).toBe('error');
			expect(fixture.session.account).toBeNull();
		}
	);

	it('uses the access subject, not ID-token identity or mutable account display fields', async () => {
		const fixture = setup();
		await fixture.session.start();
		const scope = fixture.session.scope!;
		fixture.setAccount({ ...ACCOUNT, email: 'new@nyu.edu', username: 'new_name' });
		await fixture.session.refresh();
		expect(scope.subject).toBe('auth0|ada');
		expect(fixture.session.isCurrent(scope)).toBe(true);
		expect(fixture.session.account?.username).toBe('new_name');
	});

	it('invalidates synchronously on the app-owned cross-tab logout signal', async () => {
		const store = storage();
		const fixture = setup({ store });
		await fixture.session.start();
		const old = fixture.session.scope!;
		store.setItem(IDENTITY_KEY, JSON.stringify({ subject: null, nonce: 'another-tab' }));
		fixture.notify();
		expect(fixture.session.account).toBeNull();
		expect(fixture.session.status).toBe('signed-out');
		expect(fixture.session.isCurrent(old)).toBe(false);
	});

	it('does not revive cached SDK tokens after cross-tab logout and reload', async () => {
		const store = storage();
		const before = setup({ store });
		await before.session.start();
		await before.session.logOut();
		await before.session.refresh();
		const reloaded = setup({ store });
		await reloaded.session.start();
		expect(before.session.account).toBeNull();
		expect(reloaded.session.status).toBe('signed-out');
		expect(reloaded.requests).toEqual([]);
	});

	it('invalidates private state when the SDK reports an expired session', async () => {
		const fixture = setup();
		await fixture.session.start();
		const scope = fixture.session.scope!;
		const token = Promise.withResolvers<string>();
		fixture.deferToken(token.promise);
		const credentials = fixture.session.credentialsFor(scope);
		const rejected = expect(credentials).rejects.toMatchObject({ error: 'login_required' });
		token.reject({ error: 'login_required' });
		await rejected;
		expect(fixture.session.status).toBe('signed-out');
		expect(fixture.session.account).toBeNull();
		expect(fixture.session.isCurrent(scope)).toBe(false);
	});

	it('clears the old account immediately when another tab changes principal', async () => {
		const store = storage();
		const fixture = setup({ store });
		await fixture.session.start();
		const old = fixture.session.scope!;
		const reply = Promise.withResolvers<Response>();
		fixture.deferAccount(reply.promise);
		fixture.setSubject('auth0|grace');
		store.setItem(IDENTITY_KEY, JSON.stringify({ subject: 'auth0|grace', nonce: 'switch' }));
		fixture.notify();
		expect(fixture.session.account).toBeNull();
		expect(fixture.session.isCurrent(old)).toBe(false);
		await fixture.blockedAccount;
		reply.resolve(json({ ...ACCOUNT, username: 'grace' }));
		await fixture.session.refresh();
		expect(fixture.session.scope?.subject).toBe('auth0|grace');
		expect(fixture.session.account?.username).toBe('grace');
	});

	it('does not resurrect an account from a refresh that finishes after logout', async () => {
		const fixture = setup();
		await fixture.session.start();
		const reply = Promise.withResolvers<Response>();
		fixture.deferAccount(reply.promise);
		const refresh = fixture.session.refresh();
		await fixture.blockedAccount;
		await fixture.session.logOut();
		reply.resolve(json(ACCOUNT));
		await refresh;
		expect(fixture.session.account).toBeNull();
		expect(fixture.session.status).toBe('signed-out');
	});

	it('rejects credentials acquired across logout instead of sending under an old UI scope', async () => {
		const fixture = setup();
		await fixture.session.start();
		const token = Promise.withResolvers<string>();
		fixture.deferToken(token.promise);
		const credentials = fixture.session.credentialsFor(fixture.session.scope!);
		const rejected = expect(credentials).rejects.toMatchObject({ code: 'session_changed' });
		await fixture.session.logOut();
		token.resolve(`header.${btoa(JSON.stringify({ sub: 'auth0|ada' }))}.signature`);
		await rejected;
		expect(fixture.requests).toEqual(['GET']);
	});

	it('does not resurrect an account from a late signup completion response', async () => {
		const fixture = setup({ account: { ...ACCOUNT, account_type: null } });
		await fixture.session.start();
		const reply = Promise.withResolvers<Response>();
		fixture.deferPost(reply.promise);
		const completion = fixture.session.completeSignUp({ account_type: 'student' });
		const rejected = expect(completion).rejects.toMatchObject({ code: 'session_changed' });
		await fixture.blockedPost;
		await fixture.session.logOut();
		reply.resolve(json(ACCOUNT));
		await rejected;
		expect(fixture.session.account).toBeNull();
	});
});

describe('principal-bound return after authentication', () => {
	it('keeps signup origin through callback, verification and a full reload without saving', async () => {
		const store = storage();
		const before = setup({ store, authenticated: false });
		await before.session.signUp({ account_type: 'student', username: 'ada' }, '/spots/facdb:bobst');
		const callback = setup({
			store,
			account: { ...ACCOUNT, email_verified: false, account_type: null }
		});
		expect(await callback.session.finishLogIn()).toBe('/account');
		expect(callback.requests).toEqual(['GET']);
		const reload = setup({ store, account: { ...ACCOUNT, account_type: null } });
		await reload.session.start();
		expect(reload.session.account?.account_type).toBe('student');
		expect(reload.session.consumeReturnTo()).toBe('/spots/facdb:bobst');
		expect(reload.session.consumeReturnTo()).toBeNull();
		expect(reload.requests).toEqual(['GET', 'POST']);
	});

	it('preserves another tab’s signup continuation across identity notification and reload', async () => {
		const store = storage();
		const existing = setup({ store });
		await existing.session.start();
		const signup = setup({ store, authenticated: false, subject: 'auth0|grace' });
		await signup.session.signUp(
			{ account_type: 'student', username: 'grace' },
			'/spots/facdb:bobst'
		);
		const callback = setup({
			store,
			subject: 'auth0|grace',
			account: { ...ACCOUNT, email_verified: false, account_type: null }
		});
		await callback.session.finishLogIn();
		existing.setSubject('auth0|grace');
		existing.notify();
		const reload = setup({
			store,
			subject: 'auth0|grace',
			account: { ...ACCOUNT, username: 'grace', account_type: null }
		});
		await reload.session.start();
		expect(reload.session.account?.account_type).toBe('student');
		expect(reload.session.consumeReturnTo()).toBe('/spots/facdb:bobst');
	});

	it('returns login with manual signup completion to the originating detail', async () => {
		const store = storage();
		const before = setup({ store, authenticated: false });
		await before.session.logIn('/spots/facdb:bobst');
		const after = setup({ store, account: { ...ACCOUNT, account_type: null } });
		expect(await after.session.finishLogIn()).toBe('/account');
		await after.session.completeSignUp({ account_type: 'student' });
		expect(after.session.consumeReturnTo()).toBe('/spots/facdb:bobst');
	});

	it('does not transfer a bound continuation or signup choice to another principal', async () => {
		const store = storage();
		const original = setup({
			store,
			account: { ...ACCOUNT, email_verified: false, account_type: null }
		});
		await original.session.start();
		original.session.rememberReturnTo('/spots/facdb:bobst');
		const other = setup({
			store,
			subject: 'auth0|grace',
			account: { ...ACCOUNT, account_type: null }
		});
		await other.session.finishLogIn();
		await other.session.completeSignUp({ account_type: 'student' });
		expect(other.session.consumeReturnTo()).toBeNull();
	});

	it('clears a previous origin for an unrelated authentication journey and logout', async () => {
		const fixture = setup({ authenticated: false });
		await fixture.session.logIn('/spots/facdb:bobst');
		await fixture.session.signUp();
		await fixture.session.finishLogIn();
		expect(fixture.session.consumeReturnTo()).toBeNull();
		fixture.session.rememberReturnTo('/spots/facdb:bobst');
		await fixture.session.logOut();
		expect(fixture.session.consumeReturnTo()).toBeNull();
	});

	it.each([
		'//evil.example',
		'/\\evil.example',
		'/\t/evil.example',
		'https://evil.example',
		'/.//evil.example',
		'/%2e//evil.example',
		'/a/..//evil.example'
	])('rejects external continuation %s', (value) => {
		expect(safeReturnTo(value)).toBe('/');
	});
});
