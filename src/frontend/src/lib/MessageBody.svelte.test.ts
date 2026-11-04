import { expect, it } from 'vitest';
import { page } from 'vitest/browser';
import { render } from 'vitest-browser-svelte';
import MessageBody from './MessageBody.svelte';

it('reveals only the selected spoiler and hides it again', async () => {
	render(MessageBody, { content: 'Plain ||**answer**|| then ||another||' });
	const answer = page.getByText('answer', { exact: true });
	const other = page.getByText('another', { exact: true });
	await expect.element(answer).not.toBeVisible();
	await page.getByText('Spoiler', { exact: true }).first().click();
	await expect.element(answer).toBeVisible();
	await expect.element(other).not.toBeVisible();
	await page.getByText('Spoiler', { exact: true }).first().click();
	await expect.element(answer).not.toBeVisible();
});

it('keeps code literal and treats untrusted HTML as text', async () => {
	render(MessageBody, { content: '```js\n||code||\n```\n\n||<img src=x onerror=alert(1)>||' });
	await expect.element(page.getByText('||code||')).toBeVisible();
	await page.getByText('Spoiler', { exact: true }).click();
	await expect.element(page.getByText('<img src=x onerror=alert(1)>')).toBeVisible();
	expect(document.querySelector('img[onerror]')).toBeNull();
});

it('displays a saved study sticker as its emoji equivalent', async () => {
	render(MessageBody, { content: ':sticker:study:' });
	await expect.element(page.getByText('📚')).toBeVisible();
});
