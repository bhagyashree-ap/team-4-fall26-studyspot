import { SvelteMap, SvelteSet } from 'svelte/reactivity';
import { ApiError, type Fetcher } from './api';
import type { StudySpot } from './contract';
import { listFavourites, setFavourite } from './favourites';
import { session, type Session, type SessionScope } from './session.svelte';

type Action = { desired: boolean; pending: boolean; error: string };
type LoadStatus = 'idle' | 'loading' | 'ready' | 'error';

export class Favourites {
	#session: Session;
	#fetcher: Fetcher;
	#owner = $state<SessionScope | null>(null);
	#confirmed = $state<StudySpot[]>([]);
	#actions = $state<Record<string, Action>>({});
	#status = $state<LoadStatus>('idle');
	#error = $state('');
	#hydrated = $state(false);
	#loading: Promise<void> | null = null;
	#revision = 0;
	#changedAt = new SvelteMap<string, number>();

	constructor(owner: Session, fetcher: Fetcher = (...args) => globalThis.fetch(...args)) {
		this.#session = owner;
		this.#fetcher = fetcher;
	}

	get #visible(): boolean {
		return (
			this.#session.status === 'signed-in' &&
			this.#session.account?.account_type === 'student' &&
			this.#owner?.subject === this.#session.subject &&
			this.#owner?.generation === this.#session.generation
		);
	}

	get items(): StudySpot[] {
		return this.#visible ? this.#confirmed : [];
	}
	get status(): LoadStatus {
		return this.#visible ? this.#status : 'idle';
	}
	get error(): string {
		return this.#visible ? this.#error : '';
	}

	saved(id: string): boolean | undefined {
		if (!this.#visible || !this.#hydrated) return undefined;
		return this.#confirmed.some((spot) => spot.id === id);
	}

	action(id: string): Action | undefined {
		return this.#visible ? this.#actions[id] : undefined;
	}

	#scope(): SessionScope | null {
		const scope = this.#session.scope;
		if (!scope || this.#session.account?.account_type !== 'student') return null;
		if (scope.subject !== this.#owner?.subject || scope.generation !== this.#owner?.generation) {
			this.#owner = scope;
			this.#confirmed = [];
			this.#actions = {};
			this.#status = 'idle';
			this.#error = '';
			this.#loading = null;
			this.#hydrated = false;
			this.#revision = 0;
			this.#changedAt.clear();
		}
		return this.#owner;
	}

	#current(scope: SessionScope): boolean {
		return (
			this.#session.isCurrent(scope) &&
			this.#owner === scope &&
			this.#session.account?.account_type === 'student'
		);
	}

	load({ refresh = false }: { refresh?: boolean } = {}): Promise<void> {
		const scope = this.#scope();
		if (!scope) return Promise.resolve();
		if (this.#loading) return this.#loading;
		if (!refresh && this.#status === 'ready') return Promise.resolve();
		const revision = this.#revision;
		this.#status = 'loading';
		this.#error = '';
		const loading = this.#load(scope, revision);
		this.#loading = loading;
		return loading;
	}
	#rejectEligibility(scope: SessionScope, error: ApiError): void {
		// Rebinding the same session invalidates earlier reads and actions.
		this.#owner = { subject: scope.subject, generation: scope.generation };
		this.#confirmed = [];
		this.#actions = {};
		this.#hydrated = false;
		this.#loading = null;
		this.#status = 'error';
		this.#error = error.message;
		void this.#session.refresh();
	}

	async #load(scope: SessionScope, revision: number): Promise<void> {
		try {
			const items: StudySpot[] = [];
			let offset = 0;
			for (;;) {
				const credentials = await this.#session.credentialsFor(scope);
				if (!this.#current(scope)) return;
				const page = await listFavourites(credentials, { offset, fetcher: this.#fetcher });
				if (!this.#current(scope)) return;
				items.push(...page.items);
				if (!page.pagination.has_more) break;
				offset += page.pagination.count;
			}
			const changed = new SvelteSet(
				[...this.#changedAt].filter(([, at]) => at > revision).map(([id]) => id)
			);
			const unchanged = items.filter((spot) => !changed.has(spot.id));
			const updated = this.#confirmed.filter((spot) => changed.has(spot.id));
			this.#confirmed = [
				...new SvelteMap([...updated, ...unchanged].map((spot) => [spot.id, spot])).values()
			];
			this.#hydrated = true;
			this.#status = 'ready';
		} catch (error) {
			if (this.#owner !== scope) return;
			if (error instanceof ApiError && error.status === 401) this.#session.rejectCredentials(scope);
			if (!this.#current(scope)) return;
			if (error instanceof ApiError && error.status === 409) {
				this.#rejectEligibility(scope, error);
				return;
			}
			this.#error =
				error instanceof ApiError
					? error.message
					: 'Could not load your favourites. Please try again.';
			this.#status = 'error';
		} finally {
			if (this.#current(scope)) this.#loading = null;
		}
	}

	async change(spot: StudySpot, desired: boolean): Promise<void> {
		const scope = this.#scope();
		if (!scope || this.#actions[spot.id]?.pending) return;
		if (!this.#hydrated) return;
		this.#actions[spot.id] = { desired, pending: true, error: '' };
		try {
			const credentials = await this.#session.credentialsFor(scope);
			if (!this.#current(scope)) return;
			await setFavourite(credentials, spot.id, desired, this.#fetcher);
			if (!this.#current(scope)) return;
			const exists = this.#confirmed.some((item) => item.id === spot.id);
			if (desired && !exists) this.#confirmed = [spot, ...this.#confirmed];
			if (!desired) this.#confirmed = this.#confirmed.filter((item) => item.id !== spot.id);
			this.#changedAt.set(spot.id, ++this.#revision);
			delete this.#actions[spot.id];
		} catch (error) {
			if (this.#owner !== scope) return;
			if (error instanceof ApiError && error.status === 401) this.#session.rejectCredentials(scope);
			if (!this.#current(scope)) return;
			if (error instanceof ApiError && error.status === 409) {
				this.#rejectEligibility(scope, error);
			}
			this.#actions[spot.id] = {
				desired,
				pending: false,
				error:
					error instanceof ApiError
						? error.message
						: 'Could not change this favourite. Please try again.'
			};
		}
	}
}

export const favourites = new Favourites(session);
