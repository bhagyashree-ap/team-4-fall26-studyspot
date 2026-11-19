<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { communityRequest } from './communities';
	import { searchSpots } from './api';

	type Spot = {
		id: string;
		name: string;
		address?: string | null;
		neighborhood?: string | null;
		borough?: string | null;
	};
	type Profile = {
		school: string;
		courses: string[];
		topics: string[];
		study_spot_id: string;
		visible_fields: string[];
		discoverable: boolean;
		study_spot?: Spot | null;
	};
	let school = $state('');
	let courses = $state('');
	let topics = $state('');
	let visible = $state<string[]>([]);
	let discoverable = $state(true);
	let selectedSpot = $state<Spot | null>(null);
	let spotQuery = $state('');
	let suggestions = $state<Spot[]>([]);
	let loading = $state(true);
	let saving = $state(false);
	let status = $state('');
	let timer: ReturnType<typeof setTimeout> | undefined;
	let latestSearch = 0;

	onMount(() => {
		void communityRequest<Profile & { username: string }>('/people/me')
			.then((profile) => {
				school = profile.school;
				courses = profile.courses.join(', ');
				topics = profile.topics.join(', ');
				visible = profile.visible_fields;
				discoverable = profile.discoverable;
				if (profile.study_spot_id) {
					selectedSpot = profile.study_spot ?? {
						id: profile.study_spot_id,
						name: 'Saved study spot'
					};
					spotQuery = selectedSpot.name;
				}
			})
			.catch((error: unknown) => {
				status = error instanceof Error ? error.message : 'Could not load your profile.';
			})
			.finally(() => (loading = false));
	});
	onDestroy(() => clearTimeout(timer));

	function searchSpot(value: string) {
		spotQuery = value;
		selectedSpot = null;
		suggestions = [];
		clearTimeout(timer);
		const request = ++latestSearch;
		if (value.trim().length < 2) return;
		timer = setTimeout(() => {
			void searchSpots(value.trim(), { limit: 10 })
				.then((response) => {
					if (request === latestSearch) suggestions = response.items;
				})
				.catch(() => {
					if (request === latestSearch) suggestions = [];
				});
		}, 220);
	}

	async function save() {
		saving = true;
		status = '';
		try {
			await communityRequest('/people/me', 'PUT', {
				school,
				courses: courses
					.split(',')
					.map((value) => value.trim())
					.filter(Boolean),
				topics: topics
					.split(',')
					.map((value) => value.trim())
					.filter(Boolean),
				study_spot_id: selectedSpot?.id ?? '',
				visible_fields: visible,
				discoverable
			});
			status = 'Your profile has been saved.';
		} catch (error) {
			status = error instanceof Error ? error.message : 'Could not save your profile.';
		} finally {
			saving = false;
		}
	}
</script>

<section class="profile-editor" aria-labelledby="my-profile-heading">
	<div class="heading">
		<div>
			<p class="eyebrow">STUDY PARTNER PROFILE</p>
			<h2 id="my-profile-heading">My profile</h2>
			<p>Share the details that help other students find a study partner.</p>
		</div>
	</div>
	{#if loading}<p class="status">Loading your profile…</p>
	{:else}
		<div class="fields">
			<label class="field"
				><span>School</span><input
					bind:value={school}
					maxlength="160"
					placeholder="Your school"
				/></label
			>
			<label class="field"
				><span>Courses</span><input
					bind:value={courses}
					maxlength="500"
					placeholder="CS 101, Calculus II"
				/><small>Separate courses with commas.</small></label
			>
			<label class="field"
				><span>Study topics</span><input
					bind:value={topics}
					maxlength="500"
					placeholder="Machine learning, algebra"
				/><small>Separate topics with commas.</small></label
			>
			<div class="field spot-field">
				<label for="my-study-spot">Preferred study spot</label>
				<input
					id="my-study-spot"
					value={spotQuery}
					oninput={(event) => searchSpot(event.currentTarget.value)}
					placeholder="Search spots by name or neighborhood"
					autocomplete="off"
					role="combobox"
					aria-autocomplete="list"
					aria-expanded={suggestions.length > 0}
					aria-controls="my-study-spot-options"
				/>
				{#if suggestions.length}
					<ul id="my-study-spot-options" role="listbox" aria-label="Study spot matches">
						{#each suggestions as spot (spot.id)}
							<li>
								<button
									type="button"
									role="option"
									aria-selected="false"
									onclick={() => {
										selectedSpot = spot;
										spotQuery = spot.name;
										suggestions = [];
									}}
									><strong>{spot.name}</strong><span
										>{[spot.neighborhood, spot.borough, spot.address]
											.filter(Boolean)
											.join(' · ')}</span
									></button
								>
							</li>
						{/each}
					</ul>
				{/if}
				{#if selectedSpot}<p class="selection">
						Selected: {selectedSpot.name}<button
							type="button"
							onclick={() => {
								selectedSpot = null;
								spotQuery = '';
							}}>Clear</button
						>
					</p>{/if}
			</div>
		</div>
		<fieldset>
			<legend>Show on my public profile</legend>
			<div class="checks">
				{#each [{ key: 'school', label: 'School' }, { key: 'courses', label: 'Courses' }, { key: 'topics', label: 'Study topics' }, { key: 'study_spot_id', label: 'Study spot' }] as field (field.key)}
					<label
						><input type="checkbox" value={field.key} bind:group={visible} /><span
							>{field.label}</span
						></label
					>
				{/each}
			</div>
		</fieldset>
		<div class="footer">
			<label class="discoverable"
				><input type="checkbox" bind:checked={discoverable} /><span>Show me in People search</span
				></label
			><button class="save" type="button" onclick={save} disabled={saving}
				>{saving ? 'Saving…' : 'Save profile'}</button
			>
		</div>
	{/if}
	<p class="status" role="status">{status}</p>
</section>

<style>
	.profile-editor {
		width: min(760px, 100%);
		padding: 25px;
		border: 1px solid #e8e3de;
		border-radius: 18px;
		background: #fff;
		text-align: left;
	}
	.heading {
		margin-bottom: 20px;
	}
	.eyebrow {
		margin: 0 0 7px;
		color: var(--color-brand-hover);
		font-size: 11px;
		font-weight: 750;
		letter-spacing: 0.12em;
	}
	h2 {
		margin: 0;
		color: var(--color-text);
		font-size: 24px;
		letter-spacing: -0.035em;
	}
	.heading p:last-child {
		margin: 7px 0 0;
		color: var(--color-muted);
		font-size: 14px;
		line-height: 1.5;
	}
	.fields {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 16px 20px;
	}
	.field {
		position: relative;
		display: flex;
		min-width: 0;
		flex-direction: column;
		gap: 7px;
		color: var(--color-text);
		font-size: 13px;
		font-weight: 650;
	}
	.field input {
		width: 100%;
		min-height: 43px;
		padding: 10px 12px;
		border: 1px solid #ded9d4;
		border-radius: 9px;
		color: var(--color-text);
		background: white;
		font: inherit;
		font-size: 14px;
		font-weight: 400;
	}
	.field small {
		color: var(--color-muted);
		font-size: 11px;
		font-weight: 400;
	}
	.spot-field ul {
		position: absolute;
		z-index: 4;
		top: calc(100% + 2px);
		left: 0;
		right: 0;
		max-height: 280px;
		overflow: auto;
		margin: 0;
		padding: 5px;
		list-style: none;
		border: 1px solid #ded9d4;
		border-radius: 10px;
		background: white;
		box-shadow: 0 12px 28px #28231c20;
	}
	.spot-field li button {
		display: flex;
		width: 100%;
		flex-direction: column;
		gap: 3px;
		padding: 9px 10px;
		border: 0;
		border-radius: 7px;
		color: var(--color-text);
		background: white;
		text-align: left;
		cursor: pointer;
	}
	.spot-field li button:hover,
	.spot-field li button:focus-visible {
		background: #f7f1eb;
	}
	.spot-field li strong {
		font-size: 13px;
	}
	.spot-field li span {
		color: var(--color-muted);
		font-size: 11px;
		font-weight: 400;
	}
	.selection {
		display: flex;
		align-items: center;
		gap: 10px;
		margin: 0;
		color: var(--color-muted);
		font-size: 12px;
		font-weight: 400;
	}
	.selection button {
		padding: 0;
		border: 0;
		color: var(--color-brand-hover);
		background: transparent;
		font: inherit;
		font-weight: 650;
		cursor: pointer;
	}
	fieldset {
		margin: 19px 0 0;
		padding: 0;
		border: 0;
	}
	legend {
		margin-bottom: 10px;
		font-size: 13px;
		font-weight: 700;
	}
	.checks {
		display: flex;
		flex-wrap: wrap;
		gap: 10px 22px;
	}
	.checks label,
	.discoverable {
		display: inline-flex;
		min-height: 28px;
		align-items: center;
		gap: 9px;
		color: var(--color-text);
		font-size: 13px;
		line-height: 1.35;
		cursor: pointer;
	}
	.checks input,
	.discoverable input {
		width: 17px;
		height: 17px;
		flex: none;
		margin: 0;
		accent-color: var(--color-brand-hover);
	}
	.footer {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 16px;
		margin-top: 19px;
		padding-top: 17px;
		border-top: 1px solid #eee9e4;
	}
	.save {
		min-height: 42px;
		padding: 0 18px;
		border: 1px solid #222;
		border-radius: 999px;
		color: white;
		background: #222;
		font: inherit;
		font-size: 13px;
		font-weight: 650;
		cursor: pointer;
	}
	.save:hover {
		background: #3a3a3a;
	}
	.save:disabled {
		opacity: 0.6;
		cursor: wait;
	}
	.status {
		min-height: 16px;
		margin: 9px 0 0;
		color: var(--color-muted);
		font-size: 12px;
		text-align: left;
	}
	@media (max-width: 640px) {
		.profile-editor {
			padding: 19px;
		}
		.fields {
			grid-template-columns: minmax(0, 1fr);
		}
		.footer {
			align-items: stretch;
			flex-direction: column;
		}
		.save {
			align-self: flex-start;
		}
	}
</style>
