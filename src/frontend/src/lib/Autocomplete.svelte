<script lang="ts">
	let {
		id,
		label,
		value = $bindable(),
		options,
		popular,
		placeholder,
		help,
		onOpen
	}: {
		id: string;
		label: string;
		value: string;
		options: string[];
		popular: string[];
		placeholder: string;
		help: string;
		onOpen?: () => void;
	} = $props();

	let open = $state(false);
	let active = $state(0);
	let input = $state<HTMLInputElement>();
	let matches = $derived.by(() => {
		const query = value.trim().toLocaleLowerCase();
		if (!query) return popular.slice(0, 8);
		const source = options.length ? options : popular;
		const starts = source.filter((item) => item.toLocaleLowerCase().startsWith(query)).slice(0, 8);
		if (starts.length === 8) return starts;
		return [
			...starts,
			...source
				.filter((item) => {
					const name = item.toLocaleLowerCase();
					return !name.startsWith(query) && name.includes(query);
				})
				.slice(0, 8 - starts.length)
		];
	});

	function select(choice: string) {
		value = choice;
		open = false;
		input?.focus();
	}

	function handleKeydown(event: KeyboardEvent) {
		if (event.key === 'Escape') {
			open = false;
			return;
		}
		if (!open || !matches.length) return;
		if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
			event.preventDefault();
			active = (active + (event.key === 'ArrowDown' ? 1 : -1) + matches.length) % matches.length;
		} else if (event.key === 'Enter') {
			event.preventDefault();
			select(matches[active] ?? matches[0]);
		}
	}
</script>

<div
	class="picker"
	onfocusout={(event) => {
		if (!event.currentTarget.contains(event.relatedTarget as Node | null)) open = false;
	}}
>
	<label for={id}>{label}</label>
	<input
		{id}
		bind:this={input}
		bind:value
		maxlength="100"
		{placeholder}
		autocomplete="off"
		role="combobox"
		aria-autocomplete="list"
		aria-expanded={open && matches.length > 0}
		aria-controls={`${id}-list`}
		aria-activedescendant={open && matches[active] ? `${id}-option-${active}` : undefined}
		aria-describedby={`${id}-help`}
		onfocus={() => {
			open = true;
			active = 0;
			onOpen?.();
		}}
		oninput={() => {
			open = true;
			active = 0;
		}}
		onkeydown={handleKeydown}
	/>
	{#if open && matches.length}
		<div class="suggestions">
			<p>{value.trim() ? 'Matching choices' : `Popular ${label.toLocaleLowerCase()}s`}</p>
			<div id={`${id}-list`} role="listbox" aria-label={`${label} suggestions`}>
				{#each matches as choice, index (choice)}
					<button
						id={`${id}-option-${index}`}
						type="button"
						role="option"
						aria-selected={active === index}
						onpointerdown={(event) => event.preventDefault()}
						onclick={() => select(choice)}>{choice}</button
					>
				{/each}
			</div>
		</div>
	{/if}
	<p class="help" id={`${id}-help`}>{help}</p>
</div>

<style>
	.picker {
		position: relative;
		margin: 18px 0 8px;
	}
	label {
		display: block;
		font-size: 13px;
		font-weight: 700;
		margin-bottom: 8px;
	}
	input {
		width: 100%;
		border: 1px solid #d8cdd0;
		background: white;
		border-radius: 8px;
		padding: 11px 12px;
		font: inherit;
	}
	input:focus-visible,
	button:focus-visible {
		outline: 3px solid #2458a6;
		outline-offset: 2px;
	}
	.suggestions {
		position: absolute;
		z-index: 10;
		left: 0;
		right: 0;
		top: calc(100% - 23px);
		background: white;
		border: 1px solid #d8cdd0;
		border-radius: 10px;
		box-shadow: 0 14px 30px rgb(43 20 30 / 15%);
		max-height: 315px;
		overflow-y: auto;
	}
	.suggestions p {
		margin: 0;
		padding: 10px 12px 4px;
		color: #65585d;
		font-size: 12px;
		font-weight: 700;
	}
	.suggestions button {
		display: block;
		width: 100%;
		min-height: 40px;
		padding: 9px 12px;
		border: 0;
		background: white;
		font: inherit;
		text-align: left;
		cursor: pointer;
	}
	.suggestions button:hover,
	.suggestions button[aria-selected='true'] {
		background: #f8e0e7;
	}
	.help {
		margin: 5px 0 0;
		color: #65585d;
		font-size: 12px;
	}
</style>
