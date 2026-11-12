import { describe, expect, it } from 'vitest';

import { LOCATE_OPTIONS, locate } from './near';

/** A Geolocation that answers every request the same way, recording its options. */
function geolocation(answer: (success: PositionCallback, failure: PositionErrorCallback) => void) {
	const asked: (PositionOptions | undefined)[] = [];
	const fake = {
		getCurrentPosition(
			success: PositionCallback,
			failure?: PositionErrorCallback | null,
			options?: PositionOptions
		) {
			asked.push(options);
			answer(success, failure ?? (() => {}));
		}
	} as unknown as Geolocation;
	return { fake, asked };
}

function failure(code: number): GeolocationPositionError {
	return {
		code,
		message: '',
		PERMISSION_DENIED: 1,
		POSITION_UNAVAILABLE: 2,
		TIMEOUT: 3
	} as GeolocationPositionError;
}

describe('locate', () => {
	it('returns the coordinates the browser found', async () => {
		const { fake, asked } = geolocation((success) =>
			success({ coords: { latitude: 40.7295, longitude: -73.9965 } } as GeolocationPosition)
		);

		expect(await locate(fake)).toEqual({ kind: 'found', latitude: 40.7295, longitude: -73.9965 });
		expect(asked).toEqual([LOCATE_OPTIONS]);
	});

	it('reports a refusal as denied', async () => {
		const { fake } = geolocation((_, fail) => fail(failure(1)));

		expect(await locate(fake)).toEqual({ kind: 'denied' });
	});

	it.each([
		[2, 'no position'],
		[3, 'a timeout']
	])('reports code %i, %s, as unavailable rather than denied', async (code) => {
		// Worth trying again, unlike a refusal.
		const { fake } = geolocation((_, fail) => fail(failure(code)));

		expect(await locate(fake)).toEqual({ kind: 'unavailable' });
	});

	it('reports a browser without the API as unsupported', async () => {
		expect(await locate(undefined)).toEqual({ kind: 'unsupported' });
	});

	it('asks for a coarse position, with a timeout so it cannot wait forever', () => {
		expect(LOCATE_OPTIONS.enableHighAccuracy).toBe(false);
		expect(LOCATE_OPTIONS.timeout).toBeGreaterThan(0);
	});
});
