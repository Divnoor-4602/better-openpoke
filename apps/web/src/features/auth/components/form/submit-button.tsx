import { Button as ButtonPrimitive } from '@base-ui/react/button'
import { CaretRightIcon, CircleNotchIcon } from '@phosphor-icons/react'
import { AnimatePresence, motion } from 'motion/react'

import { buttonVariants } from '@general-poke/ui/components/button'
import { cn } from '@/lib/utils'

type SubmitButtonProps = {
  children: React.ReactNode
  disabled?: boolean
  loading?: boolean
}

const MotionButtonPrimitive = motion.create(ButtonPrimitive)

export const SubmitButton = ({
  children,
  disabled,
  loading,
}: SubmitButtonProps) => {
  const interactive = !disabled && !loading

  return (
    <MotionButtonPrimitive
      aria-disabled={disabled || loading ? 'true' : undefined}
      className={cn(
        buttonVariants({
          className: 'mt-4 w-full group relative overflow-hidden',
          size: 'xl',
        }),
      )}
      data-loading={loading ? '' : undefined}
      data-slot="button"
      disabled={disabled || loading}
      type="submit"
      whileTap={{ scale: interactive ? 0.99 : 1 }}
    >
      <AnimatePresence initial={false} mode="wait">
        {loading ? (
          <motion.span
            animate={{ filter: 'blur(0px)', opacity: 1, scale: 1 }}
            aria-hidden="true"
            className="absolute inset-0 inline-flex items-center justify-center"
            data-slot="button-loading-indicator"
            exit={{ filter: 'blur(4px)', opacity: 0, scale: 0.8 }}
            initial={{ filter: 'blur(4px)', opacity: 0, scale: 0.8 }}
            key="spinner"
            transition={{ duration: 0.25, ease: 'easeOut' }}
          >
            <CircleNotchIcon className="size-4 animate-spin" weight="bold" />
          </motion.span>
        ) : (
          <motion.span
            animate={{ opacity: 1, scale: 1, y: 0 }}
            className="inline-flex items-center gap-1"
            exit={{ opacity: 0, scale: 0.9, y: 8 }}
            initial={{ opacity: 0, scale: 0.9, y: -8 }}
            key="label"
            transition={{ duration: 0.2, ease: 'easeOut' }}
          >
            <span>{children}</span>
            <span className="inline-flex -translate-x-1 opacity-0 transition-all duration-200 ease-out group-hover:translate-x-0.5 group-hover:opacity-100">
              <CaretRightIcon className="size-3.5" weight="bold" />
            </span>
          </motion.span>
        )}
      </AnimatePresence>
    </MotionButtonPrimitive>
  )
}
