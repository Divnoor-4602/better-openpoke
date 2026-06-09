import type { HTMLMotionProps } from 'motion/react'

import { cn } from '@general-poke/ui'
import { buttonVariants } from '@general-poke/ui/components/button'
import { AnimatePresence, motion } from 'motion/react'

import GoogleIcon from '@/assets/google-icon'

import type { GoogleIntegrationStatus } from '../hooks/use-google-integration'

import { getGoogleIntegrationLabel } from '../hooks/use-google-integration'

type GoogleConnectButtonProps = HTMLMotionProps<'button'> & {
  status: GoogleIntegrationStatus
}

export const GoogleConnectButton = ({
  status,
  ...props
}: GoogleConnectButtonProps) => {
  const label = getGoogleIntegrationLabel(status)

  return (
    <motion.button
      className={cn(
        buttonVariants({
          size: 'sm',
        }),
        'border-input bg-popover text-muted-foreground shadow-xs/5 hover:bg-muted hover:text-black',
        'rounded-md px-1.5 py-0.5 font-normal disabled:opacity-100',
      )}
      type="button"
      whileHover={{ scale: 1.01 }}
      whileTap={{ scale: 0.99 }}
      {...props}
    >
      <div className="flex items-center gap-1">
        <GoogleIcon className="h-3 w-auto" />
        <span className="relative inline-grid overflow-hidden">
          <AnimatePresence initial={false} mode="wait">
            <motion.span
              animate={{ filter: 'blur(0px)', opacity: 1, y: 0 }}
              exit={{ filter: 'blur(1px)', opacity: 0, y: -4 }}
              initial={{ filter: 'blur(1px)', opacity: 0, y: 4 }}
              key={label}
              transition={{ duration: 0.16, ease: 'easeOut' }}
            >
              {label}
            </motion.span>
          </AnimatePresence>
        </span>
      </div>
    </motion.button>
  )
}
