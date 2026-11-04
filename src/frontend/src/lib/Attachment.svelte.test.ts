import { it, expect, vi } from 'vitest';
import { page } from 'vitest/browser';
import { render } from 'vitest-browser-svelte';
import Attachment from './Attachment.svelte';
import { communityRequest } from './communities';

vi.mock('./communities', () => ({ communityRequest: vi.fn() }));

it.each([
	['notes.gif', 'IMG'],
	['photo.png', 'IMG'],
	['lecture.mp4', 'VIDEO'],
	['notes.html', null]
])('opens %s on demand with a download and an appropriate preview', async (name, tag) => {
	const request = vi.mocked(communityRequest);
	request.mockReset().mockResolvedValue({ data: 'YWJj' });
	render(Attachment, { url: '/dms/18/messages/42', name: name! });
	expect(request).not.toHaveBeenCalled();
	await page.getByRole('button', { name: 'Open ' + name }).click();
	await expect
		.element(page.getByRole('link', { name: 'Download ' + name }))
		.toHaveAttribute('download', name!);
	expect(request).toHaveBeenCalledWith('/dms/18/messages/42?attachment=1');
	expect(document.querySelector('img,video')?.tagName ?? null).toBe(tag);
	expect(document.querySelector('iframe,object')).toBeNull();
});
