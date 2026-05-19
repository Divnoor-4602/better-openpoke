import { CheckIcon, CopyIcon } from '@phosphor-icons/react'
import { AnimatePresence, motion } from 'motion/react'
import { useState } from 'react'

import { buttonVariants } from '@/components/ui/button'
import { useTimeout } from '@/hooks/use-timeout'
import { cn } from '@/lib/utils'

const COPIED_TIMEOUT_MS = 1500

type CopyButtonProps = {
  ariaLabelCopied?: string
  ariaLabelIdle?: string
  className?: string
  text: string
}

export const CopyButton = ({
  ariaLabelCopied = 'Copied',
  ariaLabelIdle = 'Copy',
  className,
  text,
}: CopyButtonProps) => {
  const [copied, setCopied] = useState(false)
  const iconMotionProps = {
    animate: { filter: 'blur(0px)', opacity: 1, scale: 1 },
    exit: { filter: 'blur(3px)', opacity: 0, scale: 0.6 },
    initial: { filter: 'blur(3px)', opacity: 0, scale: 0.6 },
    transition: { duration: 0.12 },
  }

  useTimeout(
    () => {
      setCopied(false)
    },
    copied ? COPIED_TIMEOUT_MS : null,
  )

  const handleCopy = async () => {
    await navigator.clipboard.writeText(text)
    setCopied(true)
  }

  const label = copied ? ariaLabelCopied : ariaLabelIdle

  return (
    <motion.button
      aria-label={label}
      className={cn(
        buttonVariants({ size: 'icon-sm', variant: 'outline' }),
        className,
      )}
      data-slot="button"
      onClick={handleCopy}
      title={label}
      type="button"
      whileTap={{ scale: 0.96 }}
    >
      <AnimatePresence initial={false} mode="popLayout">
        {copied ? (
          <motion.div key="check" {...iconMotionProps}>
            <CheckIcon />
          </motion.div>
        ) : (
          <motion.div key="copy" {...iconMotionProps}>
            <CopyIcon />
          </motion.div>
        )}
      </AnimatePresence>
    </motion.button>
  )
}
