import type { VariantProps } from 'class-variance-authority'

import { Button as ButtonPrimitive } from '@base-ui/react/button'
import { cva } from 'class-variance-authority'

import { cn } from '@general-poke/ui/lib/utils'

const buttonVariants = cva(
  "group/button relative inline-flex shrink-0 cursor-pointer appearance-none items-center justify-center rounded-md border border-transparent bg-clip-padding text-xs/relaxed font-medium whitespace-nowrap transition-shadow outline-none select-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/30 disabled:pointer-events-none disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-2 aria-invalid:ring-destructive/20 dark:aria-invalid:border-destructive/50 dark:aria-invalid:ring-destructive/40 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    defaultVariants: {
      size: 'default',
      variant: 'default',
    },
    variants: {
      size: {
        default:
          "h-7 gap-1 px-2 text-xs/relaxed has-data-[icon=inline-end]:pr-1.5 has-data-[icon=inline-start]:pl-1.5 [&_svg:not([class*='size-'])]:size-3.5",
        icon: "size-7 [&_svg:not([class*='size-'])]:size-3.5",
        'icon-lg': "size-8 [&_svg:not([class*='size-'])]:size-4",
        'icon-sm': "size-6 [&_svg:not([class*='size-'])]:size-3.5",
        'icon-xl': "size-9 [&_svg:not([class*='size-'])]:size-4",
        'icon-xs': "size-5 rounded-sm [&_svg:not([class*='size-'])]:size-2.5",
        lg: "h-8 gap-1 px-2.5 text-xs/relaxed has-data-[icon=inline-end]:pr-2 has-data-[icon=inline-start]:pl-2 [&_svg:not([class*='size-'])]:size-4",
        sm: "h-6 gap-1 px-2 text-xs/relaxed has-data-[icon=inline-end]:pr-1.5 has-data-[icon=inline-start]:pl-1.5 [&_svg:not([class*='size-'])]:size-3",
        xl: "h-9 gap-1.5 px-3 text-sm has-data-[icon=inline-end]:pr-2.5 has-data-[icon=inline-start]:pl-2.5 [&_svg:not([class*='size-'])]:size-4",
        xs: "h-5 gap-1 rounded-sm px-2 text-[0.625rem] has-data-[icon=inline-end]:pr-1.5 has-data-[icon=inline-start]:pl-1.5 [&_svg:not([class*='size-'])]:size-2.5",
      },
      variant: {
        default:
          'not-disabled:inset-shadow-[0_1px_--theme(--color-white/16%)] border-primary bg-primary text-primary-foreground shadow-primary/24 shadow-xs hover:bg-primary/90 data-pressed:bg-primary/90 [:active,[data-pressed]]:inset-shadow-[0_1px_--theme(--color-black/8%)] [:disabled,:active,[data-pressed]]:shadow-none',
        destructive:
          'not-disabled:inset-shadow-[0_1px_--theme(--color-white/16%)] border-destructive bg-destructive text-white shadow-destructive/24 shadow-xs hover:bg-destructive/90 data-pressed:bg-destructive/90 [:active,[data-pressed]]:inset-shadow-[0_1px_--theme(--color-black/8%)] [:disabled,:active,[data-pressed]]:shadow-none',
        'destructive-outline':
          'border-destructive/30 bg-popover text-destructive shadow-xs/5 hover:bg-destructive/10 data-pressed:bg-destructive/10 dark:bg-input/32 [:disabled,:active,[data-pressed]]:shadow-none',
        ghost:
          'hover:bg-muted hover:text-foreground aria-expanded:bg-muted aria-expanded:text-foreground dark:hover:bg-muted/50',
        link: 'text-primary underline-offset-4 hover:underline',
        outline:
          'border-input bg-popover text-foreground shadow-xs/5 hover:bg-accent/50 data-pressed:bg-accent/50 dark:bg-input/32 dark:data-pressed:bg-input/64 dark:hover:bg-input/64 [:disabled,:active,[data-pressed]]:shadow-none',
        secondary:
          'bg-secondary text-secondary-foreground hover:bg-secondary/80 aria-expanded:bg-secondary aria-expanded:text-secondary-foreground',
      },
    },
  },
)

type ButtonProps = ButtonPrimitive.Props &
  VariantProps<typeof buttonVariants> & {
    loading?: boolean
  }

function Button({
  children,
  className,
  disabled,
  loading = false,
  size = 'default',
  variant = 'default',
  ...props
}: ButtonProps) {
  return (
    <ButtonPrimitive
      aria-disabled={disabled || loading ? 'true' : undefined}
      className={cn(buttonVariants({ className, size, variant }))}
      data-loading={loading ? '' : undefined}
      data-slot="button"
      disabled={disabled || loading}
      {...props}
    >
      <span className={cn(loading && 'opacity-0')}>{children}</span>
      {loading && (
        <span
          aria-hidden="true"
          className="absolute inset-0 inline-flex items-center justify-center"
          data-slot="button-loading-indicator"
        >
          <span className="size-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" />
        </span>
      )}
    </ButtonPrimitive>
  )
}

export { Button, buttonVariants }
