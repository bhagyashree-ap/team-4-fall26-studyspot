<script lang="ts">
	import type { Near } from './contract';
	import type { NeighborhoodGroup } from './near';

	type Props = {
		neighborhoods: NeighborhoodGroup[];
		/** The point results are ordered from, or null for the usual order. */
		near: Near | null;
		locating: boolean;
		/** Why Near me did not work, in words for the reader; empty when it did. */
		notice: string;
		onLocate: () => void;
		onNeighborhood: (name: string) => void;
		onClear: () => void;
	};

	let { neighborhoods, near, locating, notice, onLocate, onNeighborhood, onClear }: Props =
		$props();
</script>

<div class="near" role="group" aria-label="Sort by distance">
	<div class="near-row">
		<button
			type="button"
			class="locate"
			aria-pressed={near?.kind === 'point'}
			disabled={locating}
			onclick={onLocate}
		>
			<svg viewBox="0 0 24 24" aria-hidden="true">
				<circle cx="12" cy="12" r="3.2" />
				<path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3" />
				<circle cx="12" cy="12" r="7" />
			</svg>
			{locating ? 'Finding you…' : 'Near me'}
		</button>

		<label class="field">
			<span>Near neighborhood</span>
			<!--
				Grouped by borough because 207 names in one list is a scroll, and
				the borough is how people already narrow a place in this city.
			-->
			<select
				value={near?.kind === 'neighborhood' ? near.name : ''}
				onchange={(event) => {
					const name = event.currentTarget.value;
					if (name === '') onClear();
					else onNeighborhood(name);
				}}
			>
				<option value="">Choose…</option>
				{#each neighborhoods as group (group.borough)}
					<optgroup label={group.borough}>
						{#each group.neighborhoods as name (name)}
							<option value={name}>{name}</option>
						{/each}
					</optgroup>
				{/each}
			</select>
		</label>
	</div>

	{#if near}
		<p class="sorted">
			<!--
				A neighborhood is ordered from the middle of its spots, which the
				server works out; "from" rather than "in" because spots elsewhere
				are still listed, only further down.
			-->
			Nearest first from {near.kind === 'point' ? 'your location' : near.name}.
			<button type="button" class="clear" onclick={onClear}>Stop sorting by distance</button>
		</p>
	{/if}

	{#if notice}
		<p class="notice" role="alert">{notice}</p>
	{/if}
</div>

<style>
	.near {
		display: flex;
		flex-direction: column;
		gap: 8px;
		padding: 12px 0;
	}

	.near-row {
		display: grid;
		grid-template-columns: auto minmax(0, 1fr);
		gap: 12px;
	}

	.locate {
		display: inline-flex;
		min-height: 60px;
		align-items: center;
		gap: 8px;
		padding: 0 20px;
		border: 1px solid #f0ebe7;
		border-radius: 16px;
		color: var(--color-text);
		background: #faf8f6;
		font-size: 14px;
		font-weight: 700;
		cursor: pointer;
	}

	.locate[aria-pressed='true'] {
		border-color: var(--color-brand-hover);
		color: var(--color-brand-hover);
	}

	.locate:disabled {
		cursor: progress;
		opacity: 0.7;
	}

	.locate:focus-visible,
	.clear:focus-visible,
	select:focus-visible {
		outline: 2px solid var(--color-brand-hover);
		outline-offset: 2px;
	}

	.locate svg {
		width: 18px;
		height: 18px;
		fill: none;
		stroke: currentColor;
		stroke-linecap: round;
		stroke-width: 1.8;
	}

	.field {
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
	}

	.field > span {
		color: #6a625d;
		font-size: 11px;
		font-weight: 750;
		letter-spacing: 0.06em;
		line-height: 1.2;
		text-transform: uppercase;
	}

	select {
		width: 100%;
		min-width: 0;
		min-height: 28px;
		padding: 0 20px 0 0;
		border: 0;
		color: var(--color-text);
		background-color: transparent;
		font-size: 14px;
		font-weight: 650;
	}

	.sorted,
	.notice {
		margin: 0;
		padding: 0 6px;
		font-size: 13px;
		line-height: 1.5;
	}

	.sorted {
		color: var(--color-muted);
	}

	.notice {
		color: var(--color-brand-hover);
		font-weight: 600;
	}

	.clear {
		min-height: 32px;
		padding: 0 6px;
		border: 0;
		color: var(--color-brand-hover);
		background: transparent;
		font-size: 13px;
		font-weight: 700;
		cursor: pointer;
	}

	.clear:hover {
		text-decoration: underline;
	}

	@media (max-width: 560px) {
		.near-row {
			grid-template-columns: 1fr;
		}

		.locate {
			justify-content: center;
		}
	}
</style>
