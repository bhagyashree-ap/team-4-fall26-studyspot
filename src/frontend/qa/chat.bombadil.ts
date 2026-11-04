// Explore rendered navigation recursively without posting or deleting demo data.
import { always } from '@antithesishq/bombadil';
import { actions, extract, getFingerprint, type Action } from '@antithesishq/bombadil/browser';
export {
	noUncaughtExceptions,
	noUnhandledPromiseRejections
} from '@antithesishq/bombadil/browser/defaults';

const choices = extract(({ document }) => {
	const available: Action[] = [];
	for (const element of document.querySelectorAll('button, summary')) {
		const label = element.getAttribute('aria-label') || element.textContent?.trim() || '';
		if (
			!/new message|community actions|options for #|cancel|inbox|navigation|theme|members|overview|manage|settings|close|browse communities|pinned messages|search conversation/i.test(
				label
			) &&
			!element.matches('.sidebar-item, .channel-btn')
		)
			continue;
		const bounds = element.getBoundingClientRect();
		const x = bounds.x + bounds.width / 2,
			y = bounds.y + bounds.height / 2;
		if (!element.contains(document.elementFromPoint(x, y))) continue;
		available.push({ Click: { fingerprint: getFingerprint(element), point: { x, y } } });
	}
	return available;
});
export const exploreChat = actions(() => (choices.current.length ? choices.current : ['Wait']));
const fits = extract(
	({ document, window }) => document.documentElement.scrollWidth <= window.innerWidth + 1
);
export const fitsViewport = always(() => fits.current);
const inbox = extract(({ document, window }) => {
	const panel = document.querySelector('.inbox-panel:popover-open');
	if (!panel) return true;
	const b = panel.getBoundingClientRect();
	return b.left >= 0 && b.right <= window.innerWidth + 1 && b.bottom <= window.innerHeight + 1;
});
export const inboxStaysOnScreen = always(() => inbox.current);

const centeredFeatureIcons = extract(({ document }) =>
	Array.from(document.querySelectorAll('.feature-icon')).every((badge) => {
		const svg = badge.querySelector('svg');
		if (!svg) return false;
		const outer = badge.getBoundingClientRect();
		const inner = svg.getBoundingClientRect();
		return (
			Math.abs(inner.left + inner.width / 2 - outer.left - outer.width / 2) <= 1 &&
			Math.abs(inner.top + inner.height / 2 - outer.top - outer.height / 2) <= 1
		);
	})
);
export const featureIconsStayCentered = always(() => centeredFeatureIcons.current);
