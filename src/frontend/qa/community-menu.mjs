// Run against the local guest demo. A real secondary click includes the
// pointer-up that can immediately dismiss a newly opened browser popover.
import assert from 'node:assert/strict';
import test from 'node:test';
import { chromium } from 'playwright';

test('community actions survive a right-click and dismiss with Escape or an outside click', async () => {
	const browser = await chromium.launch();
	try {
		const page = await browser.newPage();
		await page.goto('http://localhost:7500/communities');
		const community = page.locator('.community-card').first();
		const actions = page.getByRole('group', { name: 'Community actions' });
		await community.click({ button: 'right' });
		await actions.getByRole('button', { name: 'Open community' }).waitFor();
		await page.keyboard.press('Escape');
		await actions.waitFor({ state: 'hidden' });
		assert.ok(await community.evaluate((element) => element === document.activeElement));
		await community.click({ button: 'right' });
		await actions.waitFor();
		await page.getByRole('heading', { level: 1 }).click();
		await actions.waitFor({ state: 'hidden' });
	} finally {
		await browser.close();
	}
});

test('Explore joins once, reopens existing memberships and keeps navigation reachable', async () => {
	const browser = await chromium.launch();
	try {
		for (const width of [320, 768, 1280]) {
			const page = await browser.newPage({ viewport: { width, height: 844 } });
			const home = 'http://localhost:7500/communities';
			let joins = 0;
			page.on('request', (r) => {
				if (r.method() === 'POST' && r.url().endsWith('/join')) joins++;
			});
			await page.goto(home);
			const card = page.locator('.community-card').first();
			const name = (await card.getAttribute('aria-label')).replace(/^Join /, '');
			const brand = await page.getByRole('link', { name: 'StudySpot home' }).boundingBox();
			const nav = await page.getByRole('navigation', { name: 'Main navigation' }).boundingBox();
			assert.ok(
				brand.x + brand.width <= nav.x &&
					Math.abs(brand.y + brand.height / 2 - nav.y - nav.height / 2) < 2
			);
			if (width === 320) {
				const menu = page.getByRole('button', { name: 'Site navigation' });
				await menu.press('Enter');
				await page.getByRole('link', { name: 'Explore', exact: true }).waitFor();
				await page.keyboard.press('Escape');
			}
			await card.scrollIntoViewIfNeeded();
			assert.ok((await page.getByRole('link', { name: 'StudySpot home' }).boundingBox()).y >= 0);
			if (width === 768) await card.click();
			else await card.press('Enter');
			await page.getByRole('textbox', { name: /^Message #/ }).waitFor();
			const room = new URL(page.url()).searchParams.get('id');
			try {
				assert.equal(joins, 1);
				if (width === 320) await page.getByRole('button', { name: 'Toggle navigation' }).click();
				const sidebar = page.getByRole('complementary', {
					name: 'Communities and direct messages'
				});
				assert.ok((await sidebar.boundingBox()).width >= 200);
				assert.ok(await sidebar.getByText(name, { exact: true }).isVisible());
				assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
				await page.goto(home);
				await page.getByRole('button', { name: 'Open ' + name, exact: true }).click();
				await page.getByRole('textbox', { name: /^Message #/ }).waitFor();
				assert.equal(joins, 1);
			} finally {
				const csrf = (await page.context().cookies()).find((c) => c.name === 'csrftoken');
				const left = await page.request.post(
					home.replace('/communities', '/api/communities/') + room + '/leave',
					{ headers: { 'X-CSRFToken': csrf.value } }
				);
				assert.ok(left.ok());
				await page.close();
			}
		}
	} finally {
		await browser.close();
	}
});
