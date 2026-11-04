import MarkdownIt from 'markdown-it';

const markdown = new MarkdownIt({ html: false, breaks: true }).disable('image');

// Pipe is ordinary text to Markdown. Stop the text rule at a spoiler opener
// while letting backticks and escaped punctuation retain their normal meaning.
const [plainText] = markdown.inline.ruler.getRules('');
markdown.inline.ruler.at('text', (state, silent) => {
	const start = state.src.indexOf('||', state.pos);
	if (start < 0 || start >= state.posMax) return plainText(state, silent);
	if (start === state.pos) {
		const end = state.src.indexOf('||', start + 2);
		if (end > start + 2 && end + 2 <= state.posMax) {
			if (!silent) state.push('spoiler', '', 0).content = state.src.slice(start + 2, end);
			state.pos = end + 2;
			return true;
		}
		return plainText(state, silent);
	}
	const limit = state.posMax;
	state.posMax = start;
	try {
		return plainText(state, silent);
	} finally {
		state.posMax = limit;
	}
});
markdown.renderer.rules.spoiler = (tokens, index) =>
	'<details class="spoiler"><summary>Spoiler</summary><div>' +
	markdown.renderInline(tokens[index].content) +
	'</div></details>';
// A disclosure may occur in the middle of a paragraph.
markdown.renderer.rules.paragraph_open = (tokens, i) => (tokens[i].hidden ? '' : '<div>');
markdown.renderer.rules.paragraph_close = (tokens, i) => (tokens[i].hidden ? '' : '</div>\n');
export const renderMessage = (content: string) => markdown.render(content);
