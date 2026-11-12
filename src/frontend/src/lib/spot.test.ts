import { describe, expect, it } from 'vitest';
import { formatDistance } from './spot';

describe('formatDistance', () => {
	it.each([
		[0, '0 m'],
		[4, '0 m'],
		[46, '50 m'],
		[99, '100 m'],
		[100, '100 m'],
		[412, '400 m'],
		[437, '450 m']
	])('rounds %i m to %s, to 10 m under 100 m and 50 m above', (metres, expected) => {
		expect(formatDistance(metres)).toBe(expected);
	});

	it.each([
		[974, '950 m'],
		[975, '1.0 km'],
		[1000, '1.0 km'],
		[1260, '1.3 km'],
		[9949, '9.9 km'],
		[9950, '10 km'],
		[23_480, '23 km']
	])('switches to km once %i m rounds to a kilometre: %s', (metres, expected) => {
		expect(formatDistance(metres)).toBe(expected);
	});
});
