import type { ClassValue } from 'clsx'

import { clsx } from 'clsx'
import { extendTailwindMerge } from 'tailwind-merge'

// Register custom font-size utilities defined via @theme tokens in styles.css
// (e.g. --text-13) so tailwind-merge doesn't drop them when combined with a
// text color class like text-muted-foreground.
const twMerge = extendTailwindMerge({
  extend: {
    classGroups: {
      'font-size': ['text-13'],
    },
  },
})

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function stripUndefined<T extends object>(input: T): Partial<T> {
  const out: Partial<T> = {}
  for (const key of Object.keys(input) as (keyof T)[]) {
    const value = input[key]
    if (value !== undefined) {
      out[key] = value
    }
  }
  return out
}
