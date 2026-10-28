/**
 * The account page and the header, in each state a session can be in.
 *
 * The session is a real one wired to a fake Auth0 client, so what the page
 * sends when the form is submitted is the request the API would really get.
 */

import { page } from 'vitest/browser';
import { describe, expect, it } from 'vitest';
import { render } from 'vitest-browser-svelte';

import AccountPage from './AccountPage.svelte';
import type { Account } from './contract';
import { Session, type AuthClient } from './session.svelte';

const CONFIG = { enabled: true, domain: 'x.auth0.com', client_id: 'spa', audience: 'api' };

const NEW_ACCOUNT: Account = {
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

/**
 * A started session for `account`, or a signed-out one without.
 *
 * `onPost` answers `POST /account`, and every body posted is recorded.
 */
async function started(account?: Account, onPost?: (body: unknown) => Response) {
	const posted: unknown[] = [];
	const fetcher = (async (input: RequestInfo | URL, init: RequestInit = {}) => {
		if (String(input) === '/api/auth/config') return json(CONFIG);
		if (init.method === 'POST') {
			const body = JSON.parse(String(init.body));
			posted.push(body);
			return onPost ? onPost(body) : json({ ...account, ...body }, 201);
		}
		return json(account);
	}) as typeof globalThis.fetch;

	const client = {
		checkSession: async () => {},
		isAuthenticated: async () => account !== undefined,
		getTokenSilently: async () => 'token',
		getIdTokenClaims: async () => ({ __raw: 'id-token' }),
		loginWithRedirect: async () => {},
		handleRedirectCallback: async () => ({}),
		logout: async () => {}
	} as unknown as AuthClient;

	const session = new Session({ fetcher, createClient: async () => client, storage: null });
	await session.start();
	return { session, posted };
}

describe('signed out', () => {
	it('offers to sign up or log in, in the page and the header', async () => {
		const { session } = await started();
		render(AccountPage, { session });

		await expect.element(page.getByRole('heading', { name: 'Join StudySpot.' })).toBeVisible();
		await expect.element(page.getByRole('link', { name: 'Sign up' }).first()).toBeVisible();
		await expect.element(page.getByRole('button', { name: 'Log in' }).first()).toBeVisible();
	});
});

describe('finishing sign-up', () => {
	it('makes a student account', async () => {
		const { session, posted } = await started(NEW_ACCOUNT);
		render(AccountPage, { session });

		await page.getByRole('button', { name: 'Finish sign-up' }).click();

		await expect.element(page.getByText('Student account')).toBeVisible();
		expect(posted).toEqual([{ account_type: 'student' }]);
	});

	it('lets a student without an Auth0 username choose one', async () => {
		const { session, posted } = await started({ ...NEW_ACCOUNT, username: '' });
		render(AccountPage, { session });

		await page.getByRole('textbox', { name: 'Username' }).fill(' grace_h ');
		await page.getByRole('button', { name: 'Finish sign-up' }).click();

		await expect.element(page.getByRole('heading', { name: 'grace_h' })).toBeVisible();
		expect(posted).toEqual([{ account_type: 'student', username: 'grace_h' }]);
	});

	it('does not ask for a username Auth0 already has', async () => {
		const { session } = await started(NEW_ACCOUNT);
		render(AccountPage, { session });

		await expect.element(page.getByRole('button', { name: 'Finish sign-up' })).toBeVisible();
		await expect.element(page.getByRole('textbox', { name: 'Username' })).not.toBeInTheDocument();
	});

	it('asks a business for its name', async () => {
		const { session, posted } = await started({ ...NEW_ACCOUNT, username: '' });
		render(AccountPage, { session });

		await page.getByRole('radio', { name: /Business owner/ }).click();
		await page.getByRole('textbox', { name: 'Business name' }).fill('  Grumpy Coffee ');
		await page.getByRole('button', { name: 'Finish sign-up' }).click();

		await expect.element(page.getByRole('heading', { name: 'Grumpy Coffee' })).toBeVisible();
		expect(posted).toEqual([{ account_type: 'business', business_name: 'Grumpy Coffee' }]);
	});

	it('shows why the API refused', async () => {
		const message = 'A student account needs a university email address.';
		const { session } = await started({ ...NEW_ACCOUNT, email: 'ada@gmail.com' }, () =>
			json(
				{
					error: {
						code: 'validation_error',
						message: 'The request could not be validated.',
						details: [{ field: 'body.email', message, type: 'not_a_student_email' }]
					}
				},
				422
			)
		);
		render(AccountPage, { session });

		await page.getByRole('button', { name: 'Finish sign-up' }).click();

		await expect.element(page.getByRole('alert')).toHaveTextContent(message);
	});
});

describe('signed in', () => {
	it('asks for email verification before anything else', async () => {
		const { session } = await started({ ...NEW_ACCOUNT, email_verified: false });
		render(AccountPage, { session });

		await expect.element(page.getByRole('heading', { name: 'Verify your email.' })).toBeVisible();
		await expect
			.element(page.getByRole('button', { name: 'Finish sign-up' }))
			.not.toBeInTheDocument();
	});

	it('shows a finished account, and links to it from the header', async () => {
		const { session } = await started({ ...NEW_ACCOUNT, account_type: 'student' });
		render(AccountPage, { session });

		await expect.element(page.getByRole('heading', { name: 'ada', exact: true })).toBeVisible();
		// The header's account link, named for the account. Its href is not
		// checked: $app/paths has no base outside a SvelteKit build.
		await expect.element(page.getByRole('link', { name: 'ada', exact: true })).toBeVisible();
		await expect.element(page.getByRole('button', { name: 'Log out' })).toBeVisible();
	});
});
