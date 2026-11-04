import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...classes: ClassValue[]) {
	return twMerge(clsx(classes));
}
export type WithElementRef<T, U extends HTMLElement = HTMLElement> = T & { ref?: U | null };

export type WithoutChildren<T> = Omit<T, 'children'>;
