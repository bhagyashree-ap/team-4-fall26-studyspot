import assert from 'node:assert/strict';
import { execFile } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { promisify } from 'node:util';
import test from 'node:test';
import { chromium } from 'playwright';

const frontend = new URL(process.env.PUBLIC_BOARD_URL ?? 'http://127.0.0.1:7500');
const backend = new URL(process.env.PUBLIC_BOARD_BACKEND_URL ?? 'http://127.0.0.1:7501');
const database = process.env.DATABASE_URL;
const adminUsername = process.env.PUBLIC_BOARD_ADMIN_USERNAME;
const adminPassword = process.env.PUBLIC_BOARD_ADMIN_PASSWORD;
const localHosts = new Set(['127.0.0.1', 'localhost', '[::1]']);
for (const url of [frontend, backend]) {
	assert.ok(localHosts.has(url.hostname), 'Public board E2E only mutates a local application.');
}
assert.ok(database, 'Set DATABASE_URL to the dedicated local board database.');
assert.ok(
	adminUsername && adminPassword,
	'Set PUBLIC_BOARD_ADMIN_USERNAME and PUBLIC_BOARD_ADMIN_PASSWORD for the local staff account.'
);
const boardUrl = new URL('/board', frontend).href;
const apiUrl = (path) => new URL(`/api/board${path}`, frontend).href;
const run = promisify(execFile);
const backendDirectory = fileURLToPath(new URL('../../backend/', import.meta.url));

async function api(context, path, method = 'GET', data, csrf = true) {
	const cookies = await context.cookies(frontend.href);
	const token = cookies.find((cookie) => cookie.name === 'csrftoken')?.value;
	return context.request.fetch(apiUrl(path), {
		method,
		headers: {
			Origin: frontend.origin,
			...(csrf && method !== 'GET' && token ? { 'X-CSRFToken': token } : {})
		},
		...(data === undefined ? {} : { data })
	});
}

async function json(response, status = 200) {
	assert.equal(response.status(), status, await response.text());
	assert.match(response.headers()['cache-control'] ?? '', /private/);
	assert.match(response.headers()['cache-control'] ?? '', /no-store/);
	return response.json();
}

async function applyFilters(page) {
	const expected = {
		q: (await page.getByLabel('Search posts', { exact: true }).inputValue()).trim(),
		subject: (await page.getByLabel('Subject filter', { exact: true }).inputValue()).trim(),
		university: (await page.getByLabel('University filter', { exact: true }).inputValue()).trim(),
		spot: await page.getByLabel('Study spot filter', { exact: true }).inputValue(),
		kind: await page.getByLabel('Post type filter', { exact: true }).inputValue()
	};
	const response = page.waitForResponse((result) => {
		const url = new URL(result.url());
		return (
			result.request().method() === 'GET' &&
			url.pathname === '/api/board/posts' &&
			Object.entries(expected).every(([key, value]) => (url.searchParams.get(key) ?? '') === value)
		);
	});
	await page.getByRole('button', { name: 'Apply filters', exact: true }).click();
	await json(await response);
	await page.getByRole('region', { name: 'Board posts' }).waitFor();
	await page.locator('section[aria-label="Board posts"][aria-busy="false"]').waitFor();
}

async function reportEvidence(post, comment, reasonPost, reasonComment, deleted = false) {
	const payload = { post, comment, reasonPost, reasonComment, deleted };
	const code = `
import json
from board.models import Post, Comment, Report
data = json.loads(${JSON.stringify(JSON.stringify(payload))})
post_reports = Report.objects.filter(target_kind='post', target_id=data['post']['id'])
comment_reports = Report.objects.filter(target_kind='comment', target_id=data['comment']['id'])
assert post_reports.count() == 1, 'Duplicate post reports must converge'
assert comment_reports.count() == 1, 'Comment report must persist'
post_report = post_reports.get()
comment_report = comment_reports.get()
assert post_report.reason == data['reasonPost']
assert comment_report.reason == data['reasonComment']
assert post_report.target_title == data['post']['title']
assert post_report.target_body == data['post']['body']
assert comment_report.target_body == data['comment']['body']
if data['deleted']:
    assert not Post.objects.filter(pk=data['post']['id']).exists()
    assert not Comment.objects.filter(pk=data['comment']['id']).exists()
print('BOARD_E2E_DB=' + json.dumps({'post_report': post_report.pk, 'comment_report': comment_report.pk}))
`;
	const result = await run(
		fileURLToPath(new URL('../../backend/.venv/bin/python', import.meta.url)),
		['manage.py', 'shell', '--command', code],
		{
			cwd: backendDirectory,
			env: { ...process.env, DATABASE_URL: database }
		}
	);
	const line = result.stdout.split('\n').find((value) => value.startsWith('BOARD_E2E_DB='));
	assert.ok(line, result.stdout + result.stderr);
	return JSON.parse(line.slice('BOARD_E2E_DB='.length));
}

function assertPublic(value) {
	assert.deepEqual(Object.keys(value.author).sort(), ['kind', 'name']);
	for (const key of Object.keys(value)) {
		assert.ok(
			!/report|guest_id|account|email|auth0|owner_id/.test(key) || key === 'can_report',
			`Private field leaked: ${key}`
		);
	}
}

test('public board retains typed filters while author capabilities load', async () => {
	const browser = await chromium.launch();
	let release;
	const gate = new Promise((resolve) => {
		release = resolve;
	});
	try {
		const page = await browser.newPage();
		await page.route('**/api/board/access', async (route) => {
			await gate;
			await route.continue();
		});
		await page.goto(boardUrl);
		const search = page.getByLabel('Search posts', { exact: true });
		await search.fill('Startup calculus search');
		release();
		await page.getByRole('link', { name: 'New post', exact: true }).waitFor();
		assert.equal(await search.inputValue(), 'Startup calculus search');
	} finally {
		release();
		await browser.close();
	}
});

test('public board loads older feed pages without duplicates or missing posts', async () => {
	const browser = await chromium.launch();
	const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
	const posts = [];
	const keyword = `feedpage${Date.now().toString(36)}`;
	try {
		await json(await api(context, '/access'));
		for (let index = 0; index < 21; index++) {
			posts.push(
				await json(
					await api(context, '/posts', 'POST', {
						kind: 'information',
						title: `${keyword} ${index}`,
						body: 'Local feed pagination verification.',
						tags: []
					}),
					201
				)
			);
		}
		const page = await context.newPage();
		await page.goto(new URL(`/board?q=${keyword}`, frontend).href);
		await page.getByRole('link', { name: posts.at(-1).title, exact: true }).waitFor();
		const visibleIds = () =>
			page
				.locator('.board-feed [data-post-id]')
				.evaluateAll((elements) => elements.map((element) => Number(element.dataset.postId)));
		assert.deepEqual(
			await visibleIds(),
			posts
				.slice(1)
				.reverse()
				.map((post) => post.id)
		);
		await page.getByRole('button', { name: 'Load more posts', exact: true }).click();
		await page.getByRole('link', { name: posts[0].title, exact: true }).waitFor();
		assert.deepEqual(
			await visibleIds(),
			posts
				.slice()
				.reverse()
				.map((post) => post.id)
		);
		assert.equal(
			await page.getByRole('button', { name: 'Load more posts', exact: true }).count(),
			0
		);
	} finally {
		for (const post of posts) await api(context, `/posts/${post.id}`, 'DELETE');
		await browser.close();
	}
});

test(
	'public board persists real discussions, enforces ownership, preserves failed drafts, and retains private reports',
	{ timeout: 240_000 },
	async (t) => {
		t.diagnostic(
			`Writing test-owned discussions to ${frontend.origin}. Retained moderation reports remain in the local database.`
		);
		const browser = await chromium.launch();
		const owner = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
		const other = await browser.newContext({ viewport: { width: 390, height: 844 } });
		const staff = await browser.newContext();
		const page = await owner.newPage();
		const second = await other.newPage();
		const admin = await staff.newPage();
		const errors = [];
		const consoleErrors = [];
		const requests = [];
		for (const current of [page, second, admin]) {
			current.on('pageerror', (error) => errors.push(error.message));
			current.on('console', (message) => {
				if (message.type() === 'error') consoleErrors.push(message.text());
			});
			current.on('response', (response) => {
				if (new URL(response.url()).pathname.startsWith('/api/board/')) {
					requests.push(
						`${response.request().method()} ${new URL(response.url()).pathname} ${response.status()}`
					);
				}
			});
		}
		const stamp = Date.now().toString(36);
		const title = `Board ownerword${stamp}`;
		const body = `bodyword${stamp}\nSecond line stays separate.\n<script>window.boardInjected = true</script>`;
		const reasonPost = `Private post concern ${stamp}`;
		const reasonComment = `Private comment concern ${stamp}`;
		let post;
		let comment;
		let decoy;
		try {
			await page.goto(frontend.href);
			await page.getByRole('link', { name: 'Board', exact: true }).click();
			await page.getByRole('heading', { name: 'Public board', exact: true }).waitFor();
			await page.getByRole('link', { name: 'New post', exact: true }).waitFor();
			const access = await json(await api(owner, '/access'));
			assert.equal(access.viewer, 'guest');
			assert.deepEqual(access.create_kinds, ['question', 'information']);
			await page.getByRole('link', { name: 'New post', exact: true }).click();
			const composer = page.getByRole('form', { name: 'New post', exact: true });
			await composer.getByLabel('Title', { exact: true }).fill(title);
			await composer.getByLabel('Message', { exact: true }).fill(body);
			await composer.getByLabel('Subject tag', { exact: true }).fill('  Ｍａｔｈ   Ｓｔｕｄｙ  ');
			await composer.getByRole('button', { name: 'Add tag', exact: true }).click();
			await composer
				.getByLabel('Subject tag', { exact: true })
				.fill(`Biology ${stamp}${'x'.repeat(48)}`);
			await composer.getByRole('button', { name: 'Add tag', exact: true }).click();
			await composer.getByLabel('Tag type', { exact: true }).selectOption('university');
			await composer
				.getByLabel('University tag', { exact: true })
				.fill('  New   York University  ');
			await composer.getByRole('button', { name: 'Add tag', exact: true }).click();
			await composer.getByLabel('Tag type', { exact: true }).selectOption('spot');
			await composer.getByLabel('Study spot search', { exact: true }).fill('Library');
			await composer
				.getByRole('list', { name: 'Study spot results', exact: true })
				.getByRole('button')
				.first()
				.click();
			await owner.setOffline(true);
			await composer.getByRole('button', { name: 'Publish post', exact: true }).click();
			await composer.getByRole('alert').waitFor();
			assert.equal(await composer.getByLabel('Title', { exact: true }).inputValue(), title);
			assert.equal(await composer.getByLabel('Message', { exact: true }).inputValue(), body);
			assert.equal(
				await composer.getByRole('list', { name: 'Selected tags' }).locator('li').count(),
				4
			);
			await owner.setOffline(false);
			const absent = await json(await api(owner, `/posts?q=ownerword${stamp}`));
			assert.equal(absent.items.length, 0, 'Offline submission must not claim or create success');
			const created = page.waitForResponse(
				(response) =>
					response.request().method() === 'POST' &&
					new URL(response.url()).pathname === '/api/board/posts'
			);
			await composer.getByRole('button', { name: 'Publish post', exact: true }).click();
			post = await json(await created, 201);
			assertPublic(post);
			assert.equal(post.tags.filter((tag) => tag.kind === 'subject').length, 2);
			assert.ok(post.tags.some((tag) => tag.kind === 'subject' && tag.value === 'math study'));
			assert.ok(
				post.tags.some((tag) => tag.kind === 'university' && tag.value === 'new york university')
			);
			const spot = post.tags.find((tag) => tag.kind === 'spot');
			assert.ok(spot?.available);
			await page.getByRole('heading', { name: title, exact: true }).waitFor();
			const deepLink = page.url();
			assert.equal(new URL(deepLink).searchParams.get('post'), String(post.id));
			await page.reload();
			await page.getByRole('button', { name: 'Edit post', exact: true }).waitFor();
			assert.equal(await page.locator('.board-detail .board-body').textContent(), body);
			assert.equal(await page.evaluate(() => window.boardInjected), undefined);

			await second.goto(deepLink);
			await second.getByRole('heading', { name: title, exact: true }).waitFor();
			await second.getByRole('textbox', { name: 'Your comment', exact: true }).waitFor();
			assert.equal(await second.getByRole('button', { name: 'Edit post', exact: true }).count(), 0);
			assert.equal(
				await second.getByRole('button', { name: 'Delete post', exact: true }).count(),
				0
			);
			for (const method of ['PATCH', 'DELETE']) {
				const response = await api(
					other,
					`/posts/${post.id}`,
					method,
					method === 'PATCH' ? { title: 'Foreign edit' } : undefined
				);
				assert.equal(response.status(), 403, await response.text());
			}
			assert.equal((await json(await api(owner, `/posts/${post.id}`))).title, title);
			const commentCreated = second.waitForResponse(
				(response) =>
					response.request().method() === 'POST' &&
					new URL(response.url()).pathname.endsWith(`/posts/${post.id}/comments`)
			);
			await second
				.getByLabel('Your comment', { exact: true })
				.fill(`Comment ${stamp}\nA second line.`);
			await second.getByRole('button', { name: 'Post comment', exact: true }).click();
			comment = await json(await commentCreated, 201);
			assertPublic(comment);
			await second.reload();
			await second.locator(`[data-comment-id="${comment.id}"]`).waitFor();
			await page.reload();
			const foreignComment = page.locator(`[data-comment-id="${comment.id}"]`);
			await foreignComment.waitFor();
			assert.equal(
				await foreignComment.getByRole('button', { name: 'Edit comment', exact: true }).count(),
				0
			);
			assert.equal(
				await foreignComment.getByRole('button', { name: 'Delete comment', exact: true }).count(),
				0
			);
			for (const method of ['PATCH', 'DELETE']) {
				const response = await api(
					owner,
					`/comments/${comment.id}`,
					method,
					method === 'PATCH' ? { body: 'Foreign edit' } : undefined
				);
				assert.equal(response.status(), 403, await response.text());
			}
			const discussion = await json(await api(owner, `/posts/${post.id}/comments`));
			assert.equal(discussion.items.find((item) => item.id === comment.id).body, comment.body);
			for (let index = 0; index < 20; index++) {
				await json(
					await api(other, `/posts/${post.id}/comments`, 'POST', {
						body: `Pagination comment ${stamp} ${index}`
					}),
					201
				);
			}
			await page.reload();
			await page.getByRole('button', { name: 'Load more comments', exact: true }).click();
			await page.getByText(`Pagination comment ${stamp} 19`, { exact: true }).waitFor();
			assert.equal(await page.locator('[data-comment-id]').count(), 21);

			await second
				.locator('.board-detail')
				.getByRole('button', { name: 'Report post', exact: true })
				.click();
			await second.getByLabel('Reason for reporting this post', { exact: true }).fill(reasonPost);
			await second.getByRole('button', { name: 'Send report', exact: true }).click();
			await second.locator('.board-detail > .board-report').getByRole('status').waitFor();
			await json(
				await api(other, `/posts/${post.id}/reports`, 'POST', {
					reason: 'Duplicate must not replace evidence'
				}),
				200
			);
			await foreignComment.getByRole('button', { name: 'Report comment', exact: true }).click();
			await foreignComment
				.getByLabel('Reason for reporting this comment', { exact: true })
				.fill(reasonComment);
			await foreignComment.getByRole('button', { name: 'Send report', exact: true }).click();
			await foreignComment.locator('.board-report').getByRole('status').waitFor();
			const publicPost = await json(await api(other, `/posts/${post.id}`));
			const publicComments = await json(await api(other, `/posts/${post.id}/comments`));
			assertPublic(publicPost);
			publicComments.items.forEach(assertPublic);
			assert.ok(!JSON.stringify([publicPost, publicComments]).includes(reasonPost));
			assert.ok(!JSON.stringify([publicPost, publicComments]).includes(reasonComment));
			assert.ok([404, 405].includes((await api(other, `/posts/${post.id}/reports`)).status()));
			assert.ok(
				[404, 405].includes((await api(other, `/comments/${comment.id}/reports`)).status())
			);

			decoy = await json(
				await api(other, '/posts', 'POST', {
					kind: 'information',
					title: `Unrelated ${stamp}`,
					body: `Different subject ${stamp}`,
					tags: [{ kind: 'subject', value: `History ${stamp}` }]
				}),
				201
			);
			const firstPage = await json(await api(owner, `/posts?q=${stamp}&limit=1`));
			assert.equal(firstPage.has_more, true);
			const nextPage = await json(
				await api(owner, `/posts?q=${stamp}&limit=1&before=${firstPage.items[0].id}`)
			);
			assert.equal(nextPage.items[0].id, post.id);
			assert.ok(firstPage.items[0].id > nextPage.items[0].id);
			for (const term of [`ownerword${stamp}`, `bodyword${stamp}`]) {
				await page.goto(boardUrl);
				await page.getByLabel('Search posts', { exact: true }).fill(term);
				await applyFilters(page);
				assert.equal(await page.locator('.board-feed [data-post-id]').count(), 1);
				await page.getByRole('link', { name: title, exact: true }).waitFor();
			}
			await page.getByLabel('Search posts', { exact: true }).fill(stamp);
			await page.getByLabel('Subject filter', { exact: true }).fill('  MATH   study ');
			await applyFilters(page);
			assert.equal(await page.locator('.board-feed [data-post-id]').count(), 1);
			await page.getByLabel('Subject filter', { exact: true }).fill('');
			await page.getByLabel('University filter', { exact: true }).fill('NEW YORK UNIVERSITY');
			await applyFilters(page);
			assert.equal(await page.locator('.board-feed [data-post-id]').count(), 1);
			await page.getByLabel('University filter', { exact: true }).fill('');
			await page.getByLabel('Find a study spot tag', { exact: true }).fill(spot.label);
			await page
				.locator(`select[id$="-spot"] option[value="${spot.value}"]`)
				.waitFor({ state: 'attached' });
			await page.getByLabel('Study spot filter', { exact: true }).selectOption(spot.value);
			await applyFilters(page);
			assert.equal(await page.locator('.board-feed [data-post-id]').count(), 1);
			await page.getByLabel('Subject filter', { exact: true }).fill('math study');
			await page.getByLabel('University filter', { exact: true }).fill('new york university');
			await applyFilters(page);
			const filteredUrl = page.url();
			await page.getByRole('link', { name: title, exact: true }).click();
			await page.getByRole('heading', { level: 1, name: title, exact: true }).waitFor();
			assert.equal(new URL(page.url()).searchParams.get('subject'), 'math study');
			await page.reload();
			await page.getByRole('heading', { name: title, exact: true }).waitFor();
			await page.goBack();
			await page.waitForURL(filteredUrl);
			assert.equal(page.url(), filteredUrl);
			await page.getByLabel('Subject filter', { exact: true }).fill(`Absent ${stamp}`);
			await applyFilters(page);
			await page.getByRole('heading', { name: 'No matching posts', exact: true }).waitFor();
			await page.getByRole('link', { name: 'Clear filters', exact: true }).click();
			await page.getByRole('link', { name: decoy.title, exact: true }).waitFor();

			const invalidDraft = { kind: 'question', title: '', body: 'Message', tags: [] };
			await json(await api(owner, '/posts', 'POST', invalidDraft), 422);
			await json(
				await api(owner, '/posts', 'POST', { ...invalidDraft, title: 'x'.repeat(161) }),
				422
			);
			await json(
				await api(other, `/posts/${post.id}/comments`, 'POST', { body: 'x'.repeat(3001) }),
				422
			);
			await json(await api(other, `/posts/${post.id}/reports`, 'POST', { reason: '' }), 422);
			assert.equal(
				(
					await api(owner, '/posts', 'POST', { ...invalidDraft, title: 'Missing CSRF' }, false)
				).status(),
				403
			);

			await page.goto(deepLink);
			await page.getByRole('button', { name: 'Edit post', exact: true }).click();
			const edit = page.getByRole('form', { name: 'Edit post', exact: true });
			await edit.getByLabel('Title', { exact: true }).fill(`${title} updated`);
			await edit.getByLabel('Message', { exact: true }).fill(`${body}\nOwner update.`);
			await edit.getByLabel('Subject tag', { exact: true }).fill(`Updated ${stamp}`);
			await edit.getByRole('button', { name: 'Add tag', exact: true }).click();
			await edit.getByRole('button', { name: 'Save changes', exact: true }).click();
			await page.getByRole('heading', { name: `${title} updated`, exact: true }).waitFor();
			await page.reload();
			await page.getByRole('heading', { name: `${title} updated`, exact: true }).waitFor();
			assert.ok(
				(await json(await api(owner, `/posts/${post.id}`))).tags.some(
					(tag) => tag.value === `updated ${stamp}`
				)
			);
			const ownComment = second.locator(`[data-comment-id="${comment.id}"]`);
			await ownComment.getByRole('button', { name: 'Edit comment', exact: true }).click();
			await ownComment
				.getByRole('textbox', { name: 'Edit comment', exact: true })
				.fill(`Updated comment ${stamp}`);
			await ownComment.getByRole('button', { name: 'Save comment', exact: true }).click();
			await ownComment.getByText(`Updated comment ${stamp}`, { exact: true }).waitFor();
			await second.reload();
			await second
				.locator(`[data-comment-id="${comment.id}"]`)
				.getByText(`Updated comment ${stamp}`, { exact: true })
				.waitFor();
			await json(
				await api(other, `/posts/${post.id}/reports`, 'POST', {
					reason: 'Duplicate after edit must retain original evidence'
				}),
				200
			);

			const evidence = await reportEvidence(post, comment, reasonPost, reasonComment);
			await admin.goto(new URL('/admin/login/?next=/admin/board/report/', backend).href);
			await admin.getByLabel('Username:', { exact: true }).fill(adminUsername);
			await admin.getByLabel('Password:', { exact: true }).fill(adminPassword);
			await admin.getByRole('button', { name: 'Log in', exact: true }).click();
			await admin.waitForURL('**/admin/board/report/');
			await admin.goto(
				new URL(`/admin/board/report/${evidence.post_report}/change/`, backend).href
			);
			await admin.getByText(reasonPost, { exact: true }).waitFor();
			await admin.getByText(title, { exact: true }).waitFor();
			const anonymousAdmin = await other.request.get(new URL('/admin/board/report/', backend).href);
			assert.match(anonymousAdmin.url(), /\/admin\/login\//);
			assert.ok(!(await anonymousAdmin.text()).includes(reasonPost));

			for (const width of [1440, 390, 320]) {
				await page.setViewportSize({ width, height: 900 });
				assert.equal(
					await page.getByRole('button', { name: 'Site navigation', exact: true }).isVisible(),
					width <= 740,
					'Board controls must not override shared navigation visibility'
				);
				assert.ok(
					await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
					`Post overflows at ${width}px`
				);
				await page.getByRole('link', { name: 'Back to board', exact: true }).click();
				await page.getByRole('heading', { name: 'Public board', exact: true }).waitFor();
				assert.ok(
					await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
					`Feed overflows at ${width}px`
				);
				await page.getByLabel('Search posts', { exact: true }).focus();
				assert.ok(
					await page
						.getByLabel('Search posts', { exact: true })
						.evaluate((element) => element === document.activeElement)
				);
				assert.ok(
					await page
						.getByLabel('Search posts', { exact: true })
						.evaluate((element) => Number.parseFloat(getComputedStyle(element).outlineWidth) > 0)
				);
				await page.getByRole('link', { name: 'New post', exact: true }).click();
				await page.getByRole('form', { name: 'New post', exact: true }).waitFor();
				assert.ok(
					await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
					`Composer overflows at ${width}px`
				);
				for (const control of await page
					.locator(
						'.board-composer input, .board-composer select, .board-composer textarea, .board-composer button'
					)
					.all()) {
					const box = await control.boundingBox();
					assert.ok(box && box.height >= 44, `Composer target is too short at ${width}px`);
				}
				await page.getByRole('button', { name: 'Cancel', exact: true }).click();
				await page.goto(deepLink);
				await page.getByRole('heading', { name: `${title} updated`, exact: true }).waitFor();
			}
			second.once('dialog', (dialog) => dialog.dismiss());
			await second
				.locator(`[data-comment-id="${comment.id}"]`)
				.getByRole('button', { name: 'Delete comment', exact: true })
				.click();
			await second.locator(`[data-comment-id="${comment.id}"]`).waitFor();
			second.once('dialog', (dialog) => dialog.accept());
			await second
				.locator(`[data-comment-id="${comment.id}"]`)
				.getByRole('button', { name: 'Delete comment', exact: true })
				.click();
			await second.locator(`[data-comment-id="${comment.id}"]`).waitFor({ state: 'hidden' });
			page.once('dialog', (dialog) => dialog.dismiss());
			await page.getByRole('button', { name: 'Delete post', exact: true }).click();
			await page.getByRole('heading', { name: `${title} updated`, exact: true }).waitFor();
			page.once('dialog', (dialog) => dialog.accept());
			await page.getByRole('button', { name: 'Delete post', exact: true }).click();
			await page.getByRole('heading', { name: 'Public board', exact: true }).waitFor();
			assert.equal((await api(owner, `/posts/${post.id}`)).status(), 404);
			await reportEvidence(post, comment, reasonPost, reasonComment, true);
			await admin.reload();
			await admin.getByText(reasonPost, { exact: true }).waitFor();
			assert.deepEqual(errors, [], 'Unexpected uncaught browser errors');
			t.diagnostic(
				`Observed ${requests.length} real board HTTP responses. ${consoleErrors.length} console errors recorded, including intentional offline failures.`
			);
			t.diagnostic(JSON.stringify({ requests, consoleErrors }));
		} finally {
			await owner.setOffline(false);
			if (post) await api(owner, `/posts/${post.id}`, 'DELETE');
			if (decoy) await api(other, `/posts/${decoy.id}`, 'DELETE');
			await browser.close();
		}
	}
);
