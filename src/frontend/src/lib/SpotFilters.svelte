<script lang="ts">
	import type { Facets, SpotFilters } from './contract';

	type Props = {
		facets: Facets | null;
		filters: SpotFilters;
		/** `typing` when the change came keystroke by keystroke, not from a pick. */
		onChange: (filters: SpotFilters, typing?: boolean) => void;
	};

	let { facets, filters, onChange }: Props = $props();

	let active = $derived(
		Object.values(filters).filter((value) => value !== undefined && value !== '').length
	);

	/**
	 * The importer's vocabulary is snake_case, because the category belongs to
	 * the data. Presenting it is this component's job.
	 */
	function readable(value: string): string {
		const words = value.replace(/_/g, ' ');
		return words.charAt(0).toUpperCase() + words.slice(1);
	}

	function set(change: Partial<SpotFilters>, typing = false): void {
		const next = { ...filters, ...change };

		// An empty select or a cleared input means "no filter". Sent as an empty
		// string both endpoints answer 422, so the key is dropped instead.
		for (const key of Object.keys(next) as (keyof SpotFilters)[]) {
			if (next[key] === undefined || next[key] === '') delete next[key];
		}

		onChange(next, typing);
	}
</script>

<div class="filters" role="group" aria-label="Filter results">
	<!--
		The row wrappers and the `.switch` span below are not decoration: the
		stylesheet is written around them. `.toggle input` is deliberately
		hidden -- 1x1px at opacity 0 -- so that `.switch` can be the visible
		control, and without it the three toggles rendered as plain text with
		no box, no checked state and no focus ring. They still worked, which is
		why it was easy to miss.

		They were lost in a merge rather than never written: PR #34 had all of
		this, and its merge commit took one side's markup and the other side's
		stylesheet. Restored from `945b94d`.
	-->
	<div class="field-row">
		<label class="field">
			<span>Borough</span>
			<select
				value={filters.borough ?? ''}
				onchange={(event) => set({ borough: event.currentTarget.value })}
			>
				<option value="">Any</option>
				{#each facets?.boroughs ?? [] as facet (facet.value)}
					<option value={facet.value}>{facet.value} ({facet.count})</option>
				{/each}
			</select>
		</label>

		<label class="field">
			<span>Type</span>
			<select
				value={filters.category ?? ''}
				onchange={(event) => set({ category: event.currentTarget.value })}
			>
				<option value="">Any</option>
				{#each facets?.categories ?? [] as facet (facet.value)}
					<option value={facet.value}>{readable(facet.value)} ({facet.count})</option>
				{/each}
			</select>
		</label>

		<label class="field">
			<span>Campus</span>
			<!--
			A list rather than a select: there are 126 campuses, which is a
			scroll in a dropdown and a type-ahead in a datalist.

			Both handlers, and they mean different things. `oninput` is a
			keystroke, so it is debounced like the search box; `onchange` is a
			pick from the list or a blur, which should land at once. A partial
			value narrows now rather than returning nothing, so typing is worth
			following.
		-->
			<input
				list="campus-options"
				value={filters.university ?? ''}
				placeholder="Any"
				autocomplete="off"
				oninput={(event) => set({ university: event.currentTarget.value }, true)}
				onchange={(event) => set({ university: event.currentTarget.value })}
			/>
			<datalist id="campus-options">
				{#each facets?.universities ?? [] as facet (facet.value)}
					<option value={facet.value}>{facet.count}</option>
				{/each}
			</datalist>
		</label>
	</div>

	<div class="toggle-row">
		<label class="toggle">
			<input
				type="checkbox"
				checked={filters.free_public_wifi === true}
				onchange={(event) => set({ free_public_wifi: event.currentTarget.checked || undefined })}
			/>
			<!--
			"Free public Wi-Fi" rather than "has Wi-Fi": the data says a hotspot
			the city publishes is within 25 m, which a campus building's
			credentialled network is not.

			The count is how many of the currently matching spots have it, so it
			answers "is this worth ticking" before you tick it.
		-->
			<span>
				Free public Wi-Fi
				{#if facets}
					<span class="count">({facets.free_public_wifi})</span>
				{/if}
			</span>
			<span class="switch" aria-hidden="true"></span>
		</label>

		<label class="toggle">
			<input
				type="checkbox"
				checked={filters.no_purchase_needed === true}
				onchange={(event) => set({ no_purchase_needed: event.currentTarget.checked || undefined })}
			/>
			<!--
			The question a student actually asks, and not any one type: it is
			true of every library and of the campus buildings, false only of
			cafés. About money rather than entry.
		-->
			<span>
				No purchase needed
				{#if facets}
					<span class="count">({facets.no_purchase_needed})</span>
				{/if}
			</span>
			<span class="switch" aria-hidden="true"></span>
		</label>

		<label class="toggle">
			<input
				type="checkbox"
				checked={filters.indoor_seating === true}
				onchange={(event) => set({ indoor_seating: event.currentTarget.checked || undefined })}
			/>
			<!--
			"Indoor seating", matching the badge on the result card, rather than
			"Indoor seating recorded".

			The longer label was trying to carry a real caveat: unlike the two
			above it, this field is unrecorded for most spots, so ticking it
			hides the places nobody has mapped as well as the places with
			nowhere to sit. The count does that job instead, and does it
			better -- (112) against (567) and (263) says plainly that this one
			narrows hard, and it says it before you tick.
		-->
			<span>
				Indoor seating
				{#if facets}
					<span class="count">({facets.indoor_seating})</span>
				{/if}
			</span>
			<span class="switch" aria-hidden="true"></span>
		</label>
	</div>

	{#if active > 0}
		<button type="button" onclick={() => onChange({})}>
			Clear {active}
			{active === 1 ? 'filter' : 'filters'}
		</button>
	{/if}
</div>

<style>
	.filters {
		display: flex;
		width: 100%;
		flex-direction: column;
		gap: 12px;
		margin: 0;
		padding: 12px 0 0;
	}

	.field-row,
	.toggle-row {
		display: grid;
		width: 100%;
		align-items: stretch;
		gap: 12px;
	}

	.field-row {
		grid-template-columns: repeat(3, minmax(0, 1fr));
	}

	/*
		Three, matching .field-row above it, because there are three toggles.
		It was written as two when there were two, and a third in a two-column
		grid wraps onto a row of its own with an empty cell beside it.
	*/
	.toggle-row {
		grid-template-columns: repeat(3, minmax(0, 1fr));
	}

	label {
		display: flex;
		min-width: 0;
		min-height: 60px;
		flex-direction: column;
		justify-content: center;
		gap: 4px;
		padding: 9px 14px;
		border: 1px solid #f0ebe7;
		border-radius: 16px;
		background: #faf8f6;
		font-size: 14px;
		font-weight: 700;
	}

	.field > span {
		color: #6a625d;
		font-size: 11px;
		font-weight: 750;
		letter-spacing: 0.06em;
		line-height: 1.2;
		text-transform: uppercase;
	}

	select,
	input[list] {
		width: 100%;
		min-width: 0;
		min-height: 28px;
		padding: 0 20px 0 0;
		border: 0;
		border-radius: 0;
		color: var(--color-text);
		background-color: transparent;
		font-size: 14px;
		font-weight: 650;
	}

	select:focus-visible,
	input[list]:focus-visible {
		border-radius: 4px;
		outline: 2px solid var(--color-brand-hover);
		outline-offset: 2px;
	}

	.toggle {
		position: relative;
		flex-direction: row;
		align-items: center;
		justify-content: space-between;
		gap: 12px;
		min-height: 60px;
		padding: 10px 14px;
		cursor: pointer;
	}

	.toggle > span:last-child {
		flex: none;
	}

	.toggle > span:not(.switch) {
		flex: 1;
		line-height: 1.35;
	}

	.toggle .count {
		color: var(--color-muted);
		font-size: 12px;
		font-weight: 600;
	}

	.toggle input {
		position: absolute;
		top: 50%;
		left: 20px;
		width: 1px;
		height: 1px;
		margin: 0;
		transform: translateY(-50%);
		opacity: 0;
	}

	.switch {
		position: relative;
		width: 38px;
		height: 22px;
		flex: none;
		border-radius: 999px;
		background: #ded9d5;
		transition: background-color 150ms ease;
	}

	.switch::after {
		position: absolute;
		top: 3px;
		left: 3px;
		width: 16px;
		height: 16px;
		border-radius: 50%;
		background: #fff;
		box-shadow: 0 1px 3px rgb(0 0 0 / 18%);
		content: '';
		transition: transform 150ms ease;
	}

	.toggle input:checked ~ .switch {
		background: var(--color-brand-hover);
	}

	.toggle input:checked ~ .switch::after {
		transform: translateX(16px);
	}

	.toggle input:focus-visible ~ .switch {
		outline: 3px solid rgb(217 11 62 / 35%);
		outline-offset: 3px;
	}

	button {
		grid-column: 1 / -1;
		justify-self: start;
		min-height: 44px;
		padding: 0 16px;
		border: 0;
		border-radius: 999px;
		color: var(--color-brand-hover);
		background: transparent;
		font-size: 13px;
		font-weight: 700;
		cursor: pointer;
	}

	button:hover {
		text-decoration: underline;
	}

	@media (max-width: 560px) {
		.field-row,
		.toggle-row {
			grid-template-columns: 1fr;
		}
	}

	/*
		.toggle-row joins .field-row here for the same reason it now has three
		columns: at this width three of them share about 250px each, and
		"Indoor seating (112)" and its two neighbours do not fit in that.
	*/
	@media (min-width: 561px) and (max-width: 820px) {
		.field-row,
		.toggle-row {
			grid-template-columns: 1fr;
		}
	}
</style>
