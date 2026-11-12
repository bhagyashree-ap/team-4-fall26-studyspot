import { page } from 'vitest/browser';
import { beforeEach, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import Messages from './+page.svelte';

const { request } = vi.hoisted(() => ({ request: vi.fn() }));
vi.mock('$app/navigation', async (original) => ({
	...(await original<typeof import('$app/navigation')>()),
	replaceState: vi.fn(),
	goto: vi.fn()
}));
vi.mock('$lib/communities', async (original) => ({
	...(await original<typeof import('$lib/communities')>()),
	communityRequest: request
}));
const group = {
	id: 55,
	kind: 'group',
	other_name: 'Thursday study crew',
	member_count: 3,
	member_names: ['Maya Chen', 'Jordan Rivera'],
	unread_count: 0,
	updated_at: '2026-11-08T14:00:00Z'
};
const maya = {
	name: 'Maya Chen',
	community: 'Study group',
	community_id: 1,
	target: { user_id: '12' }
};
const jordan = {
	name: 'Jordan Rivera',
	community: 'Study group',
	community_id: 1,
	target: { user_id: '13' }
};
beforeEach(() => {
	request.mockReset();
	let created = false;
	request.mockImplementation(async (path: string, method = 'GET') => {
		if (path === '/communities/access') return { guest_preview: true };
		if (path === '/chat/demo') return { ready: true };
		if (path === '/dms' && method === 'POST') {
			created = true;
			return group;
		}
		if (path === '/dms') return { items: created ? [group] : [] };
		if (path.startsWith('/chat/people?q=Ma')) return { items: [maya] };
		if (path.startsWith('/chat/people?q=Jo')) return { items: [jordan] };
		if (path.endsWith('/presence')) return { typing: [], alerts: 'all', last_read: 0 };
		if (path.endsWith('/messages')) return { items: [], has_more: false };
		return {};
	});
});

it('creates a named private group from the plus menu and opens its chat', async () => {
	await page.viewport(1200, 900);
	await render(Messages);
	await page.getByRole('button', { name: 'Create conversation', exact: true }).click();
	await page.getByRole('button', { name: /New group/ }).click();
	await page.getByRole('textbox', { name: 'Group name' }).fill('Thursday study crew');
	const create = page.getByRole('button', { name: 'Create private group', exact: true });
	await expect.element(create).toBeDisabled();
	const search = page.getByRole('textbox', { name: 'Find a recipient' });
	await search.fill('Ma');
	await page.getByRole('button', { name: /Maya Chen Study group/ }).click();
	await search.fill('Jo');
	await page.getByRole('button', { name: /Jordan Rivera Study group/ }).click();
	await expect.element(create).toBeEnabled();
	await page.screenshot({ path: '../../../test-results/private-group-form.png' });
	await create.click();
	await expect
		.element(page.getByRole('heading', { name: 'Thursday study crew', exact: true, level: 2 }))
		.toBeVisible();
	expect(request).toHaveBeenCalledWith('/dms', 'POST', {
		name: 'Thursday study crew',
		participants: [
			{ community_id: 1, target: maya.target },
			{ community_id: 1, target: jordan.target }
		]
	});
	await expect
		.element(page.getByRole('textbox', { name: 'Message Thursday study crew', exact: true }))
		.toBeVisible();
});
