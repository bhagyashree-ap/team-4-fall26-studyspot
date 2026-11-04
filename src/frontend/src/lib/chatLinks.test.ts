import { expect, it } from 'vitest';
import { channelLink, messageLink } from './chatLinks';

const base = 'https://study.example/communities?dm=1#message-12';
it('shares only the intended channel, removing stale conversation state', () => {
	const url = new URL(channelLink(base, { community: 7, channel: 9 }));
	expect(url.pathname).toBe('/communities');
	expect([...url.searchParams]).toEqual([
		['id', '7'],
		['channel', '9']
	]);
	expect(url.hash).toBe('');
});
it('preserves an invite token and destination as distinct values', () => {
	const url = new URL(channelLink(base, { invite: 'a+b/c=', channel: 42 }));
	expect(url.searchParams.get('invite')).toBe('a+b/c=');
	expect(url.searchParams.get('channel')).toBe('42');
	expect(url.searchParams.has('dm')).toBe(false);
});
it.each(['?id=7&channel=9', '?dm=8'])('switches message within the same room %s', (query) => {
	const url = new URL(
		messageLink('https://study.example/communities' + query + '#message-2', 5000)
	);
	expect(url.search).toBe(query);
	expect(url.hash).toBe('#message-5000');
});
