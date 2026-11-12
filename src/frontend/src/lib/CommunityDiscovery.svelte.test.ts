import { page } from 'vitest/browser';
import { describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import CommunityDiscovery from './CommunityDiscovery.svelte';
import type { Community } from './communities';

const community: Community = {
	id: 1,
	name: 'Calculus together',
	description: 'Work through the hard problems together.',
	school: 'New York University',
	course: 'MATH 121',
	owner_id: null,
	member_count: 12,
	role: 'visitor'
};

function setup(role: Community['role'] = 'visitor') {
	const onjoin = vi.fn(async () => {});
	const onopen = vi.fn();
	const onbacktotop = vi.fn();
	render(CommunityDiscovery, {
		communities: [{ ...community, role }],
		loading: false,
		hasMore: false,
		joining: null,
		error: '',
		onjoin,
		onopen,
		oncreate: () => {},
		onmessages: () => {},
		onmore: () => {},
		onbacktotop
	});
	return { onjoin, onopen, onbacktotop };
}

describe('community discovery', () => {
	it('lets visitors preview a community before explicitly joining', async () => {
		const { onjoin, onopen } = setup();
		await page.getByRole('button', { name: /Take a look/ }).click();
		await expect.element(page.getByRole('dialog')).toBeVisible();
		expect(onjoin).not.toHaveBeenCalled();
		expect(onopen).not.toHaveBeenCalled();
		await page.getByRole('button', { name: 'Join community', exact: true }).click();
		expect(onjoin).toHaveBeenCalledWith(community);
	});

	it('closes a preview without joining and restores focus to its action', async () => {
		const { onjoin } = setup();
		const action = page.getByRole('button', {
			name: 'Take a look at Calculus together',
			exact: true
		});
		await action.click();
		await expect.element(page.getByRole('dialog')).toBeVisible();
		await page.getByRole('button', { name: 'Close community preview' }).click();
		await expect.element(action).toHaveFocus();
		expect(onjoin).not.toHaveBeenCalled();
		await action.click();
		await expect.element(page.getByRole('dialog')).toBeVisible();
	});

	it('offers a way back to the top after the community cards', async () => {
		const { onbacktotop } = setup();
		await page.getByRole('button', { name: 'Back to top' }).click();
		expect(onbacktotop).toHaveBeenCalledOnce();
	});

	it('opens chat directly for a community the person already joined', async () => {
		const { onjoin, onopen } = setup('member');
		await page.getByRole('button', { name: /Open chat/ }).click();
		expect(onopen).toHaveBeenCalledWith({ ...community, role: 'member' });
		expect(onjoin).not.toHaveBeenCalled();
	});
});
