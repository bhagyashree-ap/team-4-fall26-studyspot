import { expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import { render } from 'vitest-browser-svelte';
import EmojiPicker from './EmojiPicker.svelte';

it('finds emoji across categories and preserves the full skin-tone and profession sequence', async () => {
	const onpick = vi.fn();
	render(EmojiPicker, { onpick });
	await page.getByRole('button', { name: 'Choose emoji' }).click();
	await page
		.getByRole('textbox', { name: 'Search all emoji' })
		.fill('woman scientist: dark skin tone');
	await page.getByRole('button', { name: 'woman scientist: dark skin tone', exact: true }).click();
	expect(onpick).toHaveBeenCalledExactlyOnceWith('👩🏿‍🔬');
	await expect.element(page.getByRole('dialog')).not.toBeInTheDocument();
});

it('finds country flags by case-insensitive name when choosing a reaction', async () => {
	const onpick = vi.fn();
	render(EmojiPicker, { onpick, reaction: true });
	await page.getByRole('button', { name: 'Add reaction' }).click();
	await page.getByRole('textbox', { name: 'Search all emoji' }).fill('NEW ZEALAND');
	await page.getByRole('button', { name: 'flag: New Zealand', exact: true }).click();
	expect(onpick).toHaveBeenCalledExactlyOnceWith('🇳🇿');
});
