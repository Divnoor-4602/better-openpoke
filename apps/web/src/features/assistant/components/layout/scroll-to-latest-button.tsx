import { ArrowDownIcon } from '@phosphor-icons/react'
import { AnimatePresence, motion } from 'motion/react'
import { useStickToBottomContext } from 'use-stick-to-bottom'

import { buttonVariants } from '@/components/ui/button'
import { cn } from '@/lib/utils'

const buttonMotionProps = {
  animate: { opacity: 1, scale: 1, y: 0 },
  exit: { opacity: 0, scale: 0.4, y: 4 },
  initial: { opacity: 0, scale: 0.4, y: 4 },
  transition: { damping: 18, mass: 0.6, stiffness: 380, type: 'spring' },
} as const

export const ScrollToLatestButton = () => {
  const { isAtBottom, scrollToBottom } = useStickToBottomContext()

  return (
    <AnimatePresence initial={false}>
      {!isAtBottom && (
        <motion.div
          className="absolute bottom-3 left-1/2 z-10 -translate-x-1/2"
          key="scroll-to-latest"
          {...buttonMotionProps}
        >
          <motion.button
            aria-label="Scroll to latest message"
            className={cn(
              buttonVariants({
                className: 'rounded-full shadow-md',
                size: 'icon',
                variant: 'outline',
              }),
            )}
            data-slot="button"
            onClick={() => scrollToBottom()}
            type="button"
            whileTap={{ scale: 0.96 }}
          >
            <ArrowDownIcon />
          </motion.button>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
