import { resolve } from '$app/paths';
import { it, expect, vi } from 'vitest';
import { page } from 'vitest/browser';
import { render } from 'vitest-browser-svelte';
import ChatInbox from './ChatInbox.svelte';
import { communityRequest } from './communities';
vi.mock('./communities', () => ({ communityRequest: vi.fn() }));

it('keeps room and DM notifications with the same message ID independently navigable', async () => {
	const common = {
		id: 42,
		created_at: '2026-10-14T14:30:00Z',
		author_name: 'Maya',
		content: 'See you at four'
	};
	vi.mocked(communityRequest).mockResolvedValue({
		items: [
			{
				...common,
				channel__community_id: 2,
				channel__community__name: 'Study circle',
				channel_id: 4,
				channel__name: 'general'
			},
			{ ...common, conversation_id: 7 }
		]
	});
	render(ChatInbox);
	await page.getByRole('button', { name: 'Notification inbox' }).click();
	await expect
		.element(page.getByRole('link', { name: /Study circle/ }))
		.toHaveAttribute('href', resolve('/communities?id=2&channel=4#message-42'));
	await expect
		.element(page.getByRole('link', { name: /Direct message/ }))
		.toHaveAttribute('href', resolve('/communities?dm=7#message-42'));
	await page.getByRole('button', { name: 'Close inbox' }).click();
	await expect.element(page.getByRole('dialog')).not.toBeInTheDocument();
});
