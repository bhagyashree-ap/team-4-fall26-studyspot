type ChannelDestination =
	{ community: number; channel: number } | { invite: string; channel: number | null };

export function channelLink(base: string, target: ChannelDestination): string {
	const url = new URL(base);
	url.search = '';
	url.hash = '';
	if ('invite' in target) url.searchParams.set('invite', target.invite);
	else url.searchParams.set('id', String(target.community));
	if (target.channel !== null) url.searchParams.set('channel', String(target.channel));
	return url.href;
}

export function messageLink(room: string, message: number): string {
	const url = new URL(room);
	url.hash = 'message-' + message;
	return url.href;
}
