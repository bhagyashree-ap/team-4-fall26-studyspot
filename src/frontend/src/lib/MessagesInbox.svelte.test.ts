import { createRawSnippet } from 'svelte';
import { page } from 'vitest/browser';
import { describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import MessagesInbox from './MessagesInbox.svelte';
import type { DirectConversation } from './communities';

const conversations: DirectConversation[] = [
	{ id: 1, other_name: 'Alex Kim', unread_count: 1, updated_at: '2026-11-08T14:00:00Z' },
	{ id: 2, other_name: 'Jamie Lee', updated_at: '2026-11-07T14:00:00Z' }
];
const conversationView = createRawSnippet<[DirectConversation]>((conversation) => ({
	render: () => `<p>Conversation with ${conversation().other_name}</p>`
}));
async function setup(selected: DirectConversation | null = null) {
	const onselect = vi.fn();
	const onback = vi.fn();
	const onnew = vi.fn();
	const onnewgroup = vi.fn();
	const view = await render(MessagesInbox, {
		conversations,
		selected,
		conversationView,
		onselect,
		onback,
		onnew,
		onnewgroup
	});
	view.container.style.height = '100dvh';
	return { view, onselect, onback, onnew, onnewgroup };
}

describe('the messages inbox', () => {
	it('shows a two-pane inbox, filters conversations, and selects without closing', async () => {
		await page.viewport(1200, 900);
		const { view, onselect, onback } = await setup();
		await expect.element(page.getByRole('region', { name: 'Messages', exact: true })).toBeVisible();
		await expect
			.element(page.getByRole('heading', { name: /A conversation starts/ }))
			.toBeVisible();
		await page.screenshot({ path: '../../test-results/inbox-desktop.png' });
		await page.getByRole('textbox', { name: 'Find a conversation' }).fill('Alex');
		await expect.element(page.getByRole('button', { name: /Jamie Lee/ })).not.toBeInTheDocument();
		await page.getByRole('button', { name: /Alex Kim/ }).click();
		expect(onselect).toHaveBeenCalledWith(conversations[0]);
		await view.rerender({ selected: conversations[0] });
		await expect.element(page.getByText('Conversation with Alex Kim')).toBeVisible();
		await expect.element(page.getByRole('textbox', { name: 'Find a conversation' })).toBeVisible();
		expect(onback).not.toHaveBeenCalled();
	});
	it('returns to the welcome view from the Messages title', async () => {
		await page.viewport(1200, 900);
		const { view, onselect } = await setup(conversations[0]);
		await page.getByRole('button', { name: 'Messages', exact: true }).click();
		expect(onselect).toHaveBeenCalledWith(null);
		await view.rerender({ selected: null });
		await expect
			.element(page.getByRole('heading', { name: /A conversation starts/ }))
			.toBeVisible();
	});

	it('offers direct messages and private groups from the plus menu', async () => {
		const { onnew, onnewgroup } = await setup();
		await page.getByRole('button', { name: 'Create conversation', exact: true }).click();
		await page.getByRole('button', { name: /New group/ }).click();
		expect(onnewgroup).toHaveBeenCalledOnce();
		await page.getByRole('button', { name: 'Create conversation', exact: true }).click();
		await page.getByRole('button', { name: /New direct message/ }).click();
		expect(onnew).toHaveBeenCalledOnce();
	});
	it('shows actual unread counts and removes the badge after reading', async () => {
		const { view } = await setup();
		await expect.element(page.getByLabelText('1 unread message', { exact: true })).toBeVisible();
		await view.rerender({
			conversations: conversations.map((item) => ({ ...item, unread_count: 0 }))
		});
		await expect
			.element(page.getByLabelText('1 unread message', { exact: true }))
			.not.toBeInTheDocument();
	});

	it('uses a single pane on phones, with a way back to the conversation list', async () => {
		await page.viewport(390, 844);
		const { view, onselect } = await setup();
		await expect.element(page.getByRole('textbox', { name: 'Find a conversation' })).toBeVisible();
		await page.screenshot({ path: '../../test-results/inbox-mobile.png' });
		await view.rerender({ selected: conversations[0] });
		await expect.element(page.getByText('Conversation with Alex Kim')).toBeVisible();
		await expect
			.element(page.getByRole('textbox', { name: 'Find a conversation', includeHidden: true }))
			.not.toBeVisible();
		await page.getByRole('button', { name: 'All messages' }).click();
		expect(onselect).toHaveBeenCalledWith(null);
	});
	it('returns to communities through its back control', async () => {
		const { onback } = await setup();
		await page.getByRole('button', { name: 'Communities', exact: true }).click();
		await expect.poll(() => onback.mock.calls.length).toBe(1);
	});
});
