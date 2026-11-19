<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import SiteHeader from '$lib/SiteHeader.svelte';
	import { communityRequest } from '$lib/communities';
	type Profile = {
		username: string;
		display_name: string;
		school?: string;
		courses?: string[];
		topics?: string[];
		study_spot?: { id: string; name: string } | null;
	};
	let profile = $state<Profile | null>(null);
	let error = $state('');
	let busy = $state(false);
	onMount(() => {
		const username = page.params.username ?? '';
		void communityRequest<Profile>(`/people/${encodeURIComponent(username)}`)
			.then((value) => (profile = value))
			.catch(
				(cause: unknown) =>
					(error = cause instanceof Error ? cause.message : 'Profile unavailable.')
			);
	});
	async function message() {
		if (!profile) return;
		busy = true;
		try {
			const result = await communityRequest<{ id: number }>(
				`/people/${encodeURIComponent(profile.username)}/dm`,
				'POST',
				{}
			);
			await goto(resolve(`/messages?dm=${result.id}`));
		} catch (cause) {
			error = cause instanceof Error ? cause.message : 'Could not start a conversation.';
		} finally {
			busy = false;
		}
	}
</script>

<svelte:head
	><title>{profile ? `${profile.display_name} · StudySpot` : 'Student profile · StudySpot'}</title
	></svelte:head
>
<main class="profile-page">
	<SiteHeader /><a class="back" href={resolve('/people')}>← People</a>{#if error}<section
			class="panel"
			role="alert"
		>
			<h1>Profile unavailable</h1>
			<p>{error}</p>
		</section>{:else if profile}<section class="panel">
			<p class="eyebrow">STUDENT PROFILE</p>
			<h1>{profile.display_name}</h1>
			{#if profile.school}<p class="school">
					{profile.school}
				</p>{/if}{#if profile.courses?.length}<h2>Courses</h2>
				<p>{profile.courses.join(' · ')}</p>{/if}{#if profile.topics?.length}<h2>Study topics</h2>
				<p>{profile.topics.join(' · ')}</p>{/if}{#if profile.study_spot}<h2>Study spot</h2>
				<p>{profile.study_spot.name}</p>{/if}<button
				class="primary"
				onclick={message}
				disabled={busy}>{busy ? 'Opening…' : 'Message'}</button
			>
		</section>{/if}
</main>

<style>
	.profile-page {
		max-width: 900px;
		margin: 0 auto;
		padding: 0 24px 64px;
		color: #292923;
		font-family: Inter, ui-sans-serif, system-ui, sans-serif;
	}
	.back {
		display: inline-block;
		margin: 26px 0 18px;
		color: var(--color-brand-hover);
		font-size: 14px;
		font-weight: 650;
	}
	.panel {
		max-width: 620px;
		padding: 32px;
		border: 1px solid #e8e3de;
		border-radius: 20px;
		background: #fff;
	}
	.eyebrow {
		color: var(--color-brand-hover);
		font-size: 11px;
		font-weight: 750;
		letter-spacing: 0.13em;
	}
	.panel h1 {
		margin: 0;
		font-size: clamp(34px, 5vw, 48px);
		letter-spacing: -0.04em;
	}
	.panel h2 {
		margin: 23px 0 5px;
		font-size: 14px;
	}
	.panel p {
		color: #717169;
		font-size: 14px;
		line-height: 1.5;
	}
	.primary {
		min-height: 42px;
		margin-top: 24px;
		padding: 0 18px;
		border: 0;
		border-radius: 999px;
		color: #fff;
		background: #222;
		font: inherit;
		font-size: 13px;
		font-weight: 650;
		cursor: pointer;
	}
	.primary:disabled {
		opacity: 0.6;
		cursor: wait;
	}
	@media (max-width: 560px) {
		.profile-page {
			padding: 0 15px 42px;
		}
		.panel {
			padding: 22px;
		}
	}
</style>
