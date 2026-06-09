import { cn } from '@general-poke/ui'
import { buttonVariants } from '@general-poke/ui/components/button'
import { ArrowUpIcon, StopIcon } from '@phosphor-icons/react'
import { AnimatePresence, motion } from 'motion/react'

type SendButtonProps = {
  disabled?: boolean
  hasText?: boolean
  isStreaming?: boolean
  onClick: () => void
  onStop?: () => void
}

export const SendButton = ({
  disabled,
  hasText,
  isStreaming,
  onClick,
  onStop,
}: SendButtonProps) => {
  const showStop = !!isStreaming && !hasText
  const handleClick = () => {
    if (isStreaming && hasText) {
      onStop?.()
      onClick()
      return
    }
    if (showStop) {
      onStop?.()
      return
    }
    onClick()
  }
  const isDisabled = showStop ? !onStop : !isStreaming && (disabled || !hasText)
  const iconMotionProps = {
    animate: { filter: 'blur(0px)', opacity: 1, scale: 1 },
    exit: { filter: 'blur(3px)', opacity: 0, scale: 0.6 },
    initial: { filter: 'blur(3px)', opacity: 0, scale: 0.6 },
    transition: { duration: 0.12 },
  }

  return (
    <motion.button
      aria-label={showStop ? 'Stop generating' : 'Send message'}
      className={cn(buttonVariants({ size: 'icon', variant: 'default' }))}
      data-slot="button"
      disabled={isDisabled}
      onClick={handleClick}
      type="button"
      whileTap={isDisabled ? undefined : { scale: 0.96 }}
    >
      <AnimatePresence initial={false} mode="popLayout">
        {showStop ? (
          <motion.div key="stop" {...iconMotionProps}>
            <StopIcon className="size-5" weight="fill" />
          </motion.div>
        ) : (
          <motion.div key="send" {...iconMotionProps}>
            <ArrowUpIcon />
          </motion.div>
        )}
      </AnimatePresence>
    </motion.button>
  )
}
