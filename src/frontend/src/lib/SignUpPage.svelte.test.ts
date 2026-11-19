/**
 * StudySpot's own sign-up page: the questions it asks before Auth0, and what
 * it hands Auth0 when they are answered.
 */

import { page } from 'vitest/browser';
import { describe, expect, it } from 'vitest';
import { render } from 'vitest-browser-svelte';

import SignUpPage from './SignUpPage.svelte';
import type { UsernameCheck } from './contract';
import { Session, type AuthClient } from './session.svelte';

const CONFIG = { enabled: true, domain: 'x.auth0.com', client_id: 'spa', audience: 'api' };

function json(body: unknown, status = 200): Response {
	return new Response(JSON.stringify(body), {
		status,
		headers: { 'content-type': 'application/json' }
	});
}

/** A signed-out session, with a log of redirects and username checks. */
async function signedOut(taken: string[] = []) {
	const redirects: unknown[] = [];
	const checked: string[] = [];

	const fetcher = (async (input: RequestInfo | URL) => {
		const path = String(input);
		if (path === '/api/auth/config') return json(CONFIG);
		if (path.startsWith('/api/usernames/')) {
			const name = decodeURIComponent(path.slice('/api/usernames/'.length));
			checked.push(name);
			const free = !taken.includes(name.toLowerCase());
			const answer: UsernameCheck = {
				username: name,
				available: free,
				reason: free ? null : 'username_taken',
				message: free ? null : 'That username is taken.'
			};
			return json(answer);
		}
		return json({}, 404);
	}) as typeof globalThis.fetch;

	const client = {
		checkSession: async () => {},
		isAuthenticated: async () => false,
		loginWithRedirect: async (options: unknown) => void redirects.push(options)
	} as unknown as AuthClient;

	const session = new Session({ fetcher, createClient: async () => client, storage: null });
	await session.start();
	return { session, redirects, checked };
}

describe('the sign-up page', () => {
	it('asks a student for a username, then hands over to Auth0', async () => {
		const { session, redirects } = await signedOut();
		render(SignUpPage, { session });

		await page.getByRole('textbox', { name: 'Username' }).fill('grace_h');
		await expect.element(page.getByText('✓ grace_h is available')).toBeVisible();
		await page.getByRole('button', { name: 'Continue' }).click();

		await expect.poll(() => redirects.length).toBe(1);
		expect(redirects[0]).toMatchObject({ authorizationParams: { screen_hint: 'signup' } });
		expect(session.pending).toEqual({ account_type: 'student', username: 'grace_h' });
	});

	it('says a username is taken as it is typed', async () => {
		const { session, redirects } = await signedOut(['ada']);
		render(SignUpPage, { session });

		await page.getByRole('textbox', { name: 'Username' }).fill('Ada');
		await expect.element(page.getByText('That username is taken.')).toBeVisible();
		await page.getByRole('button', { name: 'Continue' }).click();

		await expect.element(page.getByRole('alert')).toHaveTextContent('That username is taken.');
		expect(redirects).toEqual([]);
	});

	it('catches a malformed username without asking the API', async () => {
		const { session, redirects, checked } = await signedOut();
		render(SignUpPage, { session });

		await page.getByRole('textbox', { name: 'Username' }).fill('a b');
		await page.getByRole('button', { name: 'Continue' }).click();

		await expect
			.element(page.getByRole('alert'))
			.toHaveTextContent('Use 3 to 30 letters, numbers, dots or underscores.');
		expect(checked).toEqual([]);
		expect(redirects).toEqual([]);
	});

	it('asks a business for its name', async () => {
		const { session, redirects } = await signedOut();
		render(SignUpPage, { session });

		await page.getByRole('radio', { name: /Business owner/ }).click();
		await page.getByRole('button', { name: 'Continue' }).click();
		await expect.element(page.getByRole('alert')).toHaveTextContent('Enter your business name.');

		await page.getByRole('textbox', { name: 'Business name' }).fill(' Grumpy Coffee ');
		await page.getByRole('button', { name: 'Continue' }).click();

		await expect.poll(() => redirects.length).toBe(1);
		expect(session.pending).toEqual({ account_type: 'business', business_name: 'Grumpy Coffee' });
	});

	it('points someone already signed in at their account', async () => {
		const fetcher = (async (input: RequestInfo | URL) =>
			json(
				String(input) === '/api/auth/config'
					? CONFIG
					: {
							email: 'ada@nyu.edu',
							email_verified: true,
							username: 'ada',
							account_type: 'student',
							business_name: '',
							created_at: '2026-10-27T12:00:00Z'
						}
			)) as typeof globalThis.fetch;
		const client = {
			checkSession: async () => {},
			isAuthenticated: async () => true,
			getTokenSilently: async () =>
				`header.${btoa(JSON.stringify({ sub: 'auth0|ada' }))}.signature`,
			getIdTokenClaims: async () => undefined
		} as unknown as AuthClient;
		const session = new Session({ fetcher, createClient: async () => client, storage: null });
		await session.start();
		render(SignUpPage, { session });

		await expect
			.element(page.getByRole('heading', { name: 'You’re already signed in.' }))
			.toBeVisible();
	});
});
