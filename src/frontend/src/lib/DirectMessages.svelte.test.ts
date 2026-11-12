import { page, userEvent } from 'vitest/browser';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import DirectMessages from './DirectMessages.svelte';
import type { DirectMessage } from './communities';
import './chat-theme.css';

const { request } = vi.hoisted(() => ({ request: vi.fn() }));
vi.mock('./communities', async (original) => ({
	...(await original<typeof import('./communities')>()),
	communityRequest: request
}));
const incoming: DirectMessage = {
	id: 1,
	author_name: 'Maya Chen',
	content:
		'I found a quiet table by the windows at Bobst. Want to work through the practice set together? ☕',
	mine: false,
	reply_to: null,
	created_at: '2026-11-08T14:00:00Z',
	edited_at: null,
	deleted_at: null,
	pinned_at: null,
	reactions: [{ emoji: '☕', count: 1, me: true }]
};
const own: DirectMessage = {
	...incoming,
	id: 2,
	author_name: 'You',
	mine: true,
	content: 'Yes! I’ll bring my notes. See you at 4.',
	reactions: [],
	created_at: '2026-11-08T14:02:00Z'
};
const followup: DirectMessage = {
	...incoming,
	id: 3,
	content:
		'Perfect. Start with question 6 — it looks tricky, but the last step is just the chain rule.',
	reactions: [],
	created_at: '2026-11-08T14:03:00Z'
};

beforeEach(() => {
	request.mockReset();
	request.mockImplementation(
		async (path: string, method = 'GET', body?: { content: string; reply_to?: number }) => {
			if (path.endsWith('/read')) return { last_read: 3 };
			if (path.endsWith('/presence')) return { typing: [], alerts: 'all', last_read: 3 };
			if (path.includes('?after=')) return { items: [], has_more: false };
			if (path.endsWith('/pins'))
				return { items: [{ ...incoming, pinned_at: '2026-11-08T14:10:00Z' }] };
			if (path.endsWith('/pin')) return { ...incoming, pinned_at: '2026-11-08T14:10:00Z' };
			if (path.endsWith('/messages') && method === 'POST')
				return { ...own, id: 4, content: body?.content ?? '', reply_to: body?.reply_to ?? null };
			if (path.endsWith('/messages')) return { items: [incoming, own, followup], has_more: false };
			return {};
		}
	);
});
async function setup(width = 1100) {
	await page.viewport(width, 820);
	const view = await render(DirectMessages, {
		conversation: { id: 1, other_name: 'Maya Chen', updated_at: incoming.created_at },
		presentation: 'inbox'
	});
	view.container.classList.add('chat-shell');
	view.container.style.height = '100dvh';
	view.container.style.display = 'flex';
	await expect.element(page.getByText(incoming.content, { exact: true })).toBeVisible();
	return view;
}

describe('direct message bubbles and actions', () => {
	it('shows readable incoming and outgoing messages with actions in a popover', async () => {
		await setup();
		await expect.element(page.getByRole('article', { name: 'Message from you' })).toBeVisible();
		await page.screenshot({ path: '../../test-results/dm-bubbles-desktop.png' });
		await page.getByRole('button', { name: 'Actions for message from Maya Chen' }).first().click();
		await expect.element(page.getByRole('dialog', { name: 'Message actions' })).toBeVisible();
		await Promise.all(
			page
				.getByRole('dialog', { name: 'Message actions' })
				.element()
				.getAnimations()
				.map((animation) => animation.finished)
		);
		await page.screenshot({ path: '../../test-results/dm-menu.png' });
		await page.getByRole('button', { name: 'Pin message', exact: true }).click();
		await expect
			.poll(() => request.mock.calls.some(([path]) => path === '/dms/1/messages/1/pin'))
			.toBe(true);
		await expect.element(page.getByText('Pinned', { exact: true })).toBeVisible();
	});
	it('replies to the selected message and preserves the reply when sending', async () => {
		await setup(390);
		await page.screenshot({ path: '../../test-results/dm-bubbles-mobile.png' });
		await page.getByRole('button', { name: 'Actions for message from Maya Chen' }).first().click();
		await page.getByRole('button', { name: 'Reply', exact: true }).click();
		const composer = page.getByRole('textbox', { name: 'Message Maya Chen', exact: true });
		await expect.element(composer).toHaveFocus();
		await composer.fill('I’ll start with question 6.');
		await page.getByRole('button', { name: 'Send message', exact: true }).click();
		await expect
			.poll(() =>
				request.mock.calls.some(
					([path, method, body]) =>
						path === '/dms/1/messages' && method === 'POST' && body.reply_to === 1
				)
			)
			.toBe(true);
	});
	it('exposes edit actions only for your messages and restores focus after Escape', async () => {
		await setup();
		const trigger = page.getByRole('button', { name: 'Actions for message from you', exact: true });
		await trigger.click();
		await expect
			.element(page.getByRole('button', { name: 'Edit message', exact: true }))
			.toBeVisible();
		await userEvent.keyboard('{Escape}');
		await expect.element(trigger).toHaveFocus();
		await page.getByRole('button', { name: 'Actions for message from Maya Chen' }).first().click();
		await expect
			.element(page.getByRole('button', { name: 'Edit message', exact: true }))
			.not.toBeInTheDocument();
	});
});
