import { SvelteURL } from 'svelte/reactivity';
import { Auth0Client } from '@auth0/auth0-spa-js';
import { ApiError, type Fetcher } from './api';
import {
	checkUsername,
	completeSignUp,
	fetchAccount,
	fetchAuthConfig,
	type Credentials
} from './accounts';
import type { Account, AuthConfig, CompleteSignUp, UsernameCheck } from './contract';

export type SessionStatus = 'loading' | 'disabled' | 'signed-out' | 'signed-in' | 'error';
export type SessionScope = { subject: string; generation: number };
export type AuthClient = Pick<
	Auth0Client,
	| 'checkSession'
	| 'isAuthenticated'
	| 'getTokenSilently'
	| 'getIdTokenClaims'
	| 'loginWithRedirect'
	| 'handleRedirectCallback'
	| 'logout'
>;
type Enabled = Extract<AuthConfig, { enabled: true }>;
export type PendingStore = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;
export type SessionDependencies = {
	fetcher?: Fetcher;
	createClient?: (config: Enabled) => Promise<AuthClient>;
	storage?: PendingStore | null;
	subscribeIdentity?: (listener: () => void) => void;
};
type Continuation = { returnTo: string; subject: string | null };
const PENDING_KEY = 'studyspot:pending-sign-up';
const CONTINUATION_KEY = 'studyspot:account-continuation';
export const IDENTITY_KEY = 'studyspot:identity';
export const CALLBACK_PATH = '/callback';

function browserStorage(): PendingStore | null {
	try {
		return typeof window === 'undefined' ? null : window.localStorage;
	} catch {
		return null;
	}
}

function isCompleteSignUp(value: unknown): value is CompleteSignUp {
	if (typeof value !== 'object' || value === null) return false;
	const choice = value as Record<string, unknown>;
	if (choice.account_type === 'business') return typeof choice.business_name === 'string';
	return (
		choice.account_type === 'student' &&
		(choice.username === undefined || typeof choice.username === 'string')
	);
}

// Refresh tokens avoid the third-party iframe cookies Safari and Firefox block.
async function auth0Client(config: Enabled): Promise<AuthClient> {
	return new Auth0Client({
		domain: config.domain,
		clientId: config.client_id,
		authorizationParams: {
			audience: config.audience,
			redirect_uri: `${window.location.origin}${CALLBACK_PATH}`
		},
		cacheLocation: 'localstorage',
		useRefreshTokens: true
	});
}

export function safeReturnTo(value: unknown): string {
	if (
		typeof value !== 'string' ||
		!value.startsWith('/') ||
		value.startsWith('//') ||
		value.includes('\\')
	)
		return '/';
	for (let index = 0; index < value.length; index += 1) {
		const code = value.charCodeAt(index);
		if (code <= 32 || code === 127) return '/';
	}
	try {
		const url = new SvelteURL(value, 'https://studyspot.invalid');
		if (url.origin !== 'https://studyspot.invalid') return '/';
		const path = url.pathname + url.search + url.hash;
		return path.startsWith('//') ? '/' : path;
	} catch {
		return '/';
	}
}

// This scopes browser state only. The API verifies and authorizes the token.
function accessSubject(token: string): string | null {
	try {
		const payload = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')));
		return typeof payload.sub === 'string' && payload.sub.length > 0 ? payload.sub : null;
	} catch {
		return null;
	}
}

function signalSubject(value: string | null): string | null {
	try {
		const subject: unknown = JSON.parse(value ?? 'null')?.subject;
		return typeof subject === 'string' && subject ? subject : null;
	} catch {
		return null;
	}
}

function changed(): ApiError {
	return new ApiError('session_changed', 'Your session changed. Please try again.', 401);
}

function describe(error: unknown): string {
	if (error instanceof ApiError) {
		if (error.code === 'network_error')
			return 'Could not reach StudySpot. Check your connection and try again.';
		return error.message;
	}
	const description = (error as { error_description?: unknown } | null)?.error_description;
	if (typeof description === 'string' && description)
		return `Auth0 could not log you in: ${description}`;
	return 'Something went wrong while logging in.';
}

function isLoggedOut(error: unknown): boolean {
	if (error instanceof ApiError) return error.status === 401;
	const code = (error as { error?: unknown } | null)?.error;
	return code === 'login_required' || code === 'missing_refresh_token' || code === 'invalid_grant';
}

export class Session {
	status = $state<SessionStatus>('loading');
	account = $state<Account | null>(null);
	error = $state('');
	subject = $state<string | null>(null);
	generation = $state(0);
	pending = $state<CompleteSignUp | null>(null);
	pendingError = $state<ApiError | null>(null);
	#fetcher: Fetcher;
	#createClient: (config: Enabled) => Promise<AuthClient>;
	#storage: PendingStore | null;
	#subscribeIdentity: (listener: () => void) => void;
	#client: AuthClient | null = null;
	#started: Promise<void> | null = null;
	#observedSignal: string | null;
	#continuation: Continuation | null = null;
	#pendingSubject: string | null = null;

	constructor(dependencies: SessionDependencies = {}) {
		this.#fetcher = dependencies.fetcher ?? ((...args) => globalThis.fetch(...args));
		this.#createClient = dependencies.createClient ?? auth0Client;
		this.#storage = dependencies.storage === undefined ? browserStorage() : dependencies.storage;
		this.#subscribeIdentity =
			dependencies.subscribeIdentity ??
			((listener) => {
				if (dependencies.storage !== undefined || typeof window === 'undefined') return;
				window.addEventListener('storage', (event) => {
					if (event.key === IDENTITY_KEY || event.key === null) listener();
				});
			});
		this.#observedSignal = this.#read(IDENTITY_KEY);
		try {
			const saved = JSON.parse(this.#read(PENDING_KEY) ?? 'null');
			if (isCompleteSignUp(saved?.choice)) {
				this.pending = saved.choice;
				this.#pendingSubject = typeof saved.subject === 'string' ? saved.subject : null;
			}
			const continuation = JSON.parse(this.#read(CONTINUATION_KEY) ?? 'null');
			if (
				continuation &&
				safeReturnTo(continuation.returnTo) === continuation.returnTo &&
				(continuation.subject === null || typeof continuation.subject === 'string')
			) {
				this.#continuation = continuation;
			}
		} catch {
			this.#write(PENDING_KEY, null);
			this.#write(CONTINUATION_KEY, null);
		}
	}

	get scope(): SessionScope | null {
		return this.status === 'signed-in' && this.subject
			? { subject: this.subject, generation: this.generation }
			: null;
	}

	isCurrent(scope: SessionScope): boolean {
		this.#syncIdentity();
		return (
			this.status === 'signed-in' &&
			this.subject === scope.subject &&
			this.generation === scope.generation
		);
	}

	start({ callback = false }: { callback?: boolean } = {}): Promise<void> {
		if (!this.#started) {
			this.#subscribeIdentity(() => this.#syncIdentity());
			this.#started = this.#start(callback);
		}
		return this.#started;
	}

	async #start(callback: boolean): Promise<void> {
		let generation = this.generation;
		try {
			const config = await fetchAuthConfig(this.#fetcher);
			if (!config.enabled) {
				this.status = 'disabled';
				return;
			}
			const client = await this.#createClient(config);
			this.#client = client;
			generation = this.generation;
			if (callback) return;
			if (this.#observedSignal !== null && signalSubject(this.#observedSignal) === null) {
				this.status = 'signed-out';
				return;
			}
			await client.checkSession();
			if (!this.#sameGeneration(generation)) return;
			const authenticated = await client.isAuthenticated();
			if (!this.#sameGeneration(generation)) return;
			if (authenticated) await this.#loadAccount(generation);
			else this.status = 'signed-out';
		} catch (error) {
			if (!this.#client || this.#sameGeneration(generation)) this.#fail(error);
		}
	}

	async finishLogIn(): Promise<string> {
		await this.start({ callback: true });
		const client = this.#client;
		if (!client) return '/';
		this.#invalidate('loading');
		this.#publishIdentity(null);
		const generation = this.generation;
		try {
			const { appState } = await client.handleRedirectCallback<{ returnTo?: string }>();
			if (!this.#sameGeneration(generation)) return '/';
			if (!this.#continuation) this.rememberReturnTo(appState?.returnTo ?? '/');
			await this.#loadAccount(generation, false, true);
			if (!this.#sameGeneration(generation) || !this.account) return '/account';
			if (!this.account.email_verified || this.account.account_type === null) return '/account';
			return this.consumeReturnTo() ?? '/';
		} catch (error) {
			if (this.#sameGeneration(generation)) this.#fail(error);
			return '/account';
		}
	}

	rememberReturnTo(returnTo: string): void {
		this.#continuation = { returnTo: safeReturnTo(returnTo), subject: this.subject };
		this.#write(CONTINUATION_KEY, this.#continuation);
	}

	consumeReturnTo(): string | null {
		const continuation = this.#continuation;
		if (
			!continuation ||
			!this.scope ||
			!this.account?.email_verified ||
			this.account.account_type === null
		)
			return null;
		this.#continuation = null;
		this.#write(CONTINUATION_KEY, null);
		return continuation.subject === this.subject ? continuation.returnTo : null;
	}

	async logIn(returnTo = '/'): Promise<void> {
		this.#writePending(null);
		this.rememberReturnTo(returnTo);
		await this.#redirect(returnTo, {});
	}

	async signUp(choice?: CompleteSignUp, returnTo = '/account'): Promise<void> {
		this.rememberReturnTo(returnTo);
		this.#writePending(choice ?? null);
		await this.#redirect(returnTo, { screen_hint: 'signup' });
	}

	async logOut(): Promise<void> {
		const client = this.#client;
		this.#invalidate('signed-out');
		this.#clearJourney();
		this.#publishIdentity(null);
		if (client) await client.logout({ logoutParams: { returnTo: window.location.origin } });
	}

	async refresh(): Promise<void> {
		if (!this.#client || this.status === 'signed-out' || this.status === 'disabled') return;
		const generation = this.generation;
		try {
			await this.#loadAccount(generation, true);
		} catch (error) {
			if (this.#sameGeneration(generation)) this.#fail(error);
		}
	}

	checkUsername(username: string): Promise<UsernameCheck> {
		return checkUsername(username, this.#fetcher);
	}

	async completeSignUp(choice: CompleteSignUp): Promise<Account> {
		const scope = this.scope;
		if (!scope) throw changed();
		const credentials = await this.credentialsFor(scope);
		if (!this.isCurrent(scope)) throw changed();
		const account = await completeSignUp(credentials, choice, this.#fetcher);
		if (!this.isCurrent(scope)) throw changed();
		this.account = account;
		this.#writePending(null);
		return account;
	}

	async #redirect(returnTo: string, authorizationParams: Record<string, string>): Promise<void> {
		const generation = this.generation;
		await this.start();
		if (!this.#sameGeneration(generation) || !this.#client) return;
		await this.#client.loginWithRedirect({
			appState: { returnTo: safeReturnTo(returnTo) },
			authorizationParams
		});
	}

	async credentialsFor(scope: SessionScope): Promise<Credentials> {
		if (!this.isCurrent(scope)) throw changed();
		try {
			return await this.#credentials(scope.generation, false, scope.subject);
		} catch (error) {
			if (isLoggedOut(error)) this.rejectCredentials(scope);
			throw error;
		}
	}

	rejectCredentials(scope: SessionScope): void {
		if (!this.isCurrent(scope)) return;
		this.#invalidate('signed-out');
		this.#clearJourney();
		this.#publishIdentity(null);
	}

	communityCredentials(): Promise<Credentials> | null {
		const scope = this.scope;
		return scope ? this.credentialsFor(scope) : null;
	}

	async #credentials(
		generation: number,
		fresh = false,
		expected: string | null = this.subject
	): Promise<Credentials> {
		if (!this.#sameGeneration(generation)) throw changed();
		const access = fresh
			? await this.#client?.getTokenSilently({ cacheMode: 'off' })
			: await this.#client?.getTokenSilently();
		if (!this.#sameGeneration(generation)) throw changed();
		const subject = access ? accessSubject(access) : null;
		if (!access || !subject) {
			this.#invalidate('signed-out');
			this.#clearJourney();
			this.#publishIdentity(null);
			throw new ApiError('unauthorized', 'You are not logged in.', 401);
		}
		if (expected && expected !== subject) {
			this.#invalidate('signed-out');
			this.#clearJourney();
			this.#publishIdentity(null);
			throw changed();
		}
		const id = (await this.#client?.getIdTokenClaims())?.__raw;
		if (!this.#sameGeneration(generation)) throw changed();
		if (!this.subject) {
			this.subject = subject;
			this.#bindJourney(subject);
			this.#publishIdentity(subject);
		}
		return { access, id };
	}

	async #loadAccount(generation: number, fresh = false, callback = false): Promise<void> {
		try {
			const expected = callback ? null : (this.subject ?? signalSubject(this.#observedSignal));
			const credentials = await this.#credentials(generation, fresh, expected);
			if (!this.#sameGeneration(generation)) return;
			const subject = this.subject;
			const account = await fetchAccount(credentials, this.#fetcher);
			if (!this.#sameGeneration(generation) || this.subject !== subject) return;
			this.account = account;
			this.status = 'signed-in';
			this.error = '';
			await this.#applyPending();
		} catch (error) {
			if (!this.#sameGeneration(generation)) return;
			if (!isLoggedOut(error)) throw error;
			this.#invalidate('signed-out');
			this.#clearJourney();
			this.#publishIdentity(null);
		}
	}

	async #applyPending(): Promise<void> {
		const account = this.account;
		if (!account || !this.pending) return;
		if (account.account_type !== null || this.#pendingSubject !== this.subject) {
			this.#writePending(null);
			return;
		}
		if (!account.email_verified) return;
		const scope = this.scope;
		try {
			await this.completeSignUp(this.pending);
		} catch (error) {
			if (!scope || !this.isCurrent(scope)) return;
			if (!(error instanceof ApiError) || isLoggedOut(error)) throw error;
			this.pendingError = error;
		}
	}

	#bindJourney(subject: string): void {
		if (this.#continuation) {
			if (this.#continuation.subject && this.#continuation.subject !== subject) {
				this.#continuation = null;
			} else this.#continuation = { ...this.#continuation, subject };
			this.#write(CONTINUATION_KEY, this.#continuation);
		}
		if (this.pending) {
			if (this.#pendingSubject && this.#pendingSubject !== subject) this.#writePending(null);
			else this.#writePending(this.pending, subject);
		}
	}

	#writePending(choice: CompleteSignUp | null, subject = this.subject): void {
		this.pending = choice;
		this.#pendingSubject = choice ? subject : null;
		this.pendingError = null;
		this.#write(PENDING_KEY, choice ? { choice, subject } : null);
	}

	#clearJourney(): void {
		this.#writePending(null);
		this.#continuation = null;
		this.#write(CONTINUATION_KEY, null);
	}

	#invalidate(status: SessionStatus): void {
		this.generation += 1;
		this.subject = null;
		this.account = null;
		this.error = '';
		this.status = status;
	}

	#sameGeneration(generation: number): boolean {
		this.#syncIdentity();
		return this.generation === generation;
	}

	#syncIdentity(): void {
		if (!this.#storage) return;
		let signal: string | null;
		try {
			signal = this.#storage.getItem(IDENTITY_KEY);
		} catch {
			return;
		}
		if (signal === this.#observedSignal) return;
		this.#observedSignal = signal;
		if (!this.#client) return;
		const subject = signalSubject(signal);
		this.#invalidate(subject ? 'loading' : 'signed-out');
		this.pending = null;
		this.pendingError = null;
		this.#pendingSubject = null;
		this.#continuation = null;
		if (subject && this.#client) void this.refresh();
	}

	#publishIdentity(subject: string | null): void {
		if (subject && signalSubject(this.#observedSignal) === subject) return;
		this.#observedSignal = JSON.stringify({ subject, nonce: Math.random().toString(36).slice(2) });
		try {
			this.#storage?.setItem(IDENTITY_KEY, this.#observedSignal);
		} catch {
			this.#storage = null;
		}
	}

	#read(key: string): string | null {
		try {
			return this.#storage?.getItem(key) ?? null;
		} catch {
			return null;
		}
	}

	#write(key: string, value: unknown): void {
		try {
			if (value === null) this.#storage?.removeItem(key);
			else this.#storage?.setItem(key, JSON.stringify(value));
		} catch {
			// Browsers may deny storage while the in-memory session remains usable.
		}
	}

	#fail(error: unknown): void {
		this.account = null;
		this.error = describe(error);
		this.status = 'error';
	}
}

export const session = new Session();
