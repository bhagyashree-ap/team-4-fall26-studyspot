import { describe, expect, it } from 'vitest';
import { ApiError } from './api';
import {
	checkUsername,
	completeSignUp,
	displayName,
	fetchAccount,
	fetchAuthConfig
} from './accounts';
import type { Account } from './contract';

const ACCOUNT: Account = {
	email: 'ada@nyu.edu',
	email_verified: true,
	username: 'ada',
	account_type: null,
	business_name: '',
	created_at: '2026-10-27T12:00:00Z'
};

function json(body: unknown, status = 200): Response {
	return new Response(JSON.stringify(body), {
		status,
		headers: { 'content-type': 'application/json' }
	});
}

/** A fetcher that records what it was asked for and answers with `response`. */
function recording(response: () => Response) {
	const calls: { path: string; init: RequestInit }[] = [];
	const fetcher = (async (input: RequestInfo | URL, init: RequestInit = {}) => {
		calls.push({ path: String(input), init });
		return response();
	}) as typeof globalThis.fetch;
	return { calls, fetcher };
}

describe('fetchAuthConfig', () => {
	it('reads the tenant from the API', async () => {
		const config = { enabled: true, domain: 'x.auth0.com', client_id: 'c', audience: 'a' };
		const { calls, fetcher } = recording(() => json(config));

		expect(await fetchAuthConfig(fetcher)).toEqual(config);
		expect(calls[0].path).toBe('/api/auth/config');
	});
});

describe('fetchAccount', () => {
	it('sends the access token as a bearer token', async () => {
		const { calls, fetcher } = recording(() => json(ACCOUNT));

		expect(await fetchAccount({ access: 't0k3n' }, fetcher)).toEqual(ACCOUNT);
		expect(calls[0].path).toBe('/api/account');
		expect(new Headers(calls[0].init.headers).get('authorization')).toBe('Bearer t0k3n');
	});

	it('sends the ID token alongside, when there is one', async () => {
		const { calls, fetcher } = recording(() => json(ACCOUNT));

		await fetchAccount({ access: 'a', id: 'i' }, fetcher);
		await fetchAccount({ access: 'a' }, fetcher);

		expect(new Headers(calls[0].init.headers).get('x-id-token')).toBe('i');
		expect(new Headers(calls[1].init.headers).has('x-id-token')).toBe(false);
	});

	it('reports a refused token in the API’s own words', async () => {
		const { fetcher } = recording(() =>
			json(
				{ error: { code: 'unauthorized', message: 'The access token is not valid.', details: [] } },
				401
			)
		);

		await expect(fetchAccount({ access: 'bad' }, fetcher)).rejects.toMatchObject({
			code: 'unauthorized',
			status: 401,
			message: 'The access token is not valid.'
		});
	});

	it('reports a network failure as its own code', async () => {
		const fetcher = (async () => {
			throw new TypeError('Failed to fetch');
		}) as typeof globalThis.fetch;

		await expect(fetchAccount({ access: 't' }, fetcher)).rejects.toMatchObject({
			code: 'network_error'
		});
	});
});

describe('completeSignUp', () => {
	it('posts the choice as JSON', async () => {
		const { calls, fetcher } = recording(() => json({ ...ACCOUNT, account_type: 'student' }, 201));

		const account = await completeSignUp({ access: 't' }, { account_type: 'student' }, fetcher);

		expect(account.account_type).toBe('student');
		expect(calls[0].init.method).toBe('POST');
		expect(JSON.parse(String(calls[0].init.body))).toEqual({ account_type: 'student' });
		expect(new Headers(calls[0].init.headers).get('content-type')).toBe('application/json');
	});

	it('keeps the per-field details of a validation error', async () => {
		const details = [
			{
				field: 'body.email',
				message: 'A student account needs a university email address.',
				type: 'not_a_student_email'
			}
		];
		const { fetcher } = recording(() =>
			json({ error: { code: 'validation_error', message: 'Invalid.', details } }, 422)
		);

		const failure = await completeSignUp(
			{ access: 't' },
			{ account_type: 'student' },
			fetcher
		).catch((error: unknown) => error);

		expect(failure).toBeInstanceOf(ApiError);
		expect((failure as ApiError).details).toEqual(details);
	});
});

describe('displayName', () => {
	it('prefers the business name, then the username, then the email', () => {
		expect(displayName({ ...ACCOUNT, business_name: 'Grumpy' })).toBe('Grumpy');
		expect(displayName(ACCOUNT)).toBe('ada');
		expect(displayName({ ...ACCOUNT, username: '' })).toBe('ada@nyu.edu');
	});
});

describe('checkUsername', () => {
	it('asks about the name, escaped', async () => {
		const answer = {
			username: 'a b',
			available: false,
			reason: 'invalid_username',
			message: 'No.'
		};
		const { calls, fetcher } = recording(() => json(answer));

		expect(await checkUsername('a b', fetcher)).toEqual(answer);
		expect(calls[0].path).toBe('/api/usernames/a%20b');
	});
});
