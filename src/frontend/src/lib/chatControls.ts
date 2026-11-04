// Native toolbar and navigation buttons keep their DOM bindings and layout while
// sharing the same interaction states as the shadcn Button component.
import { buttonVariants } from '$lib/components/ui/button';

export const chatControls = {
	primary: buttonVariants(),
	outline: buttonVariants({ variant: 'outline', size: 'sm' }),
	danger: buttonVariants({ variant: 'destructive', size: 'sm' }),
	icon: buttonVariants({ variant: 'ghost', size: 'icon' }),
	ghost: buttonVariants({ variant: 'ghost', size: 'sm' }),
	row: buttonVariants({
		variant: 'ghost',
		class: 'h-auto min-w-0 justify-start whitespace-normal text-left'
	})
};
