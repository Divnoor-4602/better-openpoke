import type { HTMLMotionProps } from 'motion/react'

import { motion } from 'motion/react'

import { buttonVariants } from '@/components/ui/button'
import { cn } from '@/lib/utils'

export type ChipButtonProps = HTMLMotionProps<'button'>

export const ChipButton = ({
  children,
  className,
  type = 'button',
  whileTap = { scale: 0.99 },
  ...props
}: ChipButtonProps) => {
  return (
    <motion.button
      className={cn(
        buttonVariants({ size: 'sm' }),
        'border-input bg-white text-muted-foreground shadow-xs/5 hover:bg-muted hover:text-black',
        'rounded-md px-1.5 py-0.5 font-normal',
        className,
      )}
      type={type}
      whileTap={whileTap}
      {...props}
    >
      {children}
    </motion.button>
  )
}
