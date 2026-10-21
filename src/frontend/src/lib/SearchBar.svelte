<script lang="ts">
	type Props = {
		/** What the box shows. The page owns it; this component never stores it. */
		value: string;
		/** Every keystroke, so the page's copy is never behind the box. */
		onInput: (query: string) => void;
		onSearch: (query: string) => void;
	};

	let { value, onInput, onSearch }: Props = $props();

	/**
	 * An empty submit is a real request, not a no-op.
	 *
	 * Clearing the text and pressing Search is how you say "no query any more",
	 * and swallowing it meant a deleted word went on applying to everything the
	 * page did next.
	 */
	function handleSubmit(event: SubmitEvent): void {
		event.preventDefault();
		onSearch(value.trim());
	}
</script>

<form role="search" onsubmit={handleSubmit}>
	<label for="spot-search">
		<span>Where</span>
		<input
			id="spot-search"
			name="q"
			{value}
			oninput={(event) => onInput(event.currentTarget.value)}
			placeholder="Café, public space, or neighborhood"
			autocomplete="off"
		/>
	</label>

	<button type="submit">
		<svg viewBox="0 0 24 24" aria-hidden="true">
			<circle cx="11" cy="11" r="6.5"></circle>
			<path d="m16 16 4 4"></path>
		</svg>
		<span>Search</span>
	</button>
</form>

<style>
	form {
		display: grid;
		grid-template-columns: 1fr auto;
		width: min(760px, 100%);
		padding: 8px;
		border: 1px solid var(--color-border);
		border-radius: 18px;
		background: white;
		box-shadow: 0 18px 50px rgb(34 34 34 / 12%);
		text-align: left;
	}

	label {
		display: flex;
		min-width: 0;
		flex-direction: column;
		justify-content: center;
		gap: 5px;
		padding: 9px 20px;
	}

	label span {
		color: #6a625d;
		font-size: 11px;
		font-weight: 700;
		letter-spacing: 0.06em;
		text-transform: uppercase;
	}

	input {
		min-width: 0;
		padding: 0;
		border: 0;
		outline: 0;
		color: var(--color-muted);
		background: transparent;
		font-size: 14px;
		line-height: 1.4;
	}

	button {
		display: flex;
		min-width: 132px;
		align-items: center;
		justify-content: center;
		gap: 9px;
		border: 0;
		border-radius: 12px;
		color: white;
		background: var(--color-brand);
		font-size: 14px;
		font-weight: 700;
		cursor: pointer;
		transition: background 160ms ease;
	}

	button:hover {
		background: var(--color-brand-hover);
	}

	svg {
		width: 20px;
		fill: none;
		stroke: currentColor;
		stroke-linecap: round;
		stroke-width: 2;
	}

	@media (max-width: 560px) {
		form {
			grid-template-columns: 1fr;
		}

		label {
			min-height: 64px;
		}

		button {
			min-height: 50px;
		}
	}
</style>
