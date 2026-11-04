import { expect, it } from 'vitest';
import { mergeMessages } from './history';
it('keeps one ordered row per ID across overlapping, repeated pages and edits', () => {
	const initial = [{ id: 2, content: 'old' }];
	const pages = [
		[
			{ id: 3, content: 'new' },
			{ id: 2, content: 'edited' }
		],
		[
			{ id: 1, content: 'earlier' },
			{ id: 2, content: 'edited' }
		],
		[{ id: 1, content: 'earlier' }],
		[{ id: 3, content: '' }]
	];
	let messages = initial;
	const seen = new Set([2]);
	for (const page of pages) {
		messages = mergeMessages(messages, page);
		for (const row of page) seen.add(row.id);
		expect(messages.map((m) => m.id)).toEqual([...seen].sort((a, b) => a - b));
		expect(mergeMessages(messages, page)).toEqual(messages);
	}
	expect(messages.map((m) => m.content)).toEqual(['earlier', 'edited', '']);
	expect(initial).toEqual([{ id: 2, content: 'old' }]);
});
