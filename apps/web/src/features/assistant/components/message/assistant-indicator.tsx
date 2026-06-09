import { ShimmeringText } from '@general-poke/ui/components/shimmering-text'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'

import { GeneralMagicLogo } from '@/assets/general-magic-logo'

import type { AssistantState } from '../../lib/agent-state'

const RESTING_COLORS = {
  bottomLeft: '#fb923c',
  bottomRight: '#fed7aa',
  topLeft: '#c2410c',
  topRight: '#f97316',
}

const ERROR_COLORS = {
  bottomLeft: 'var(--destructive)',
  bottomRight: 'var(--destructive)',
  topLeft: 'var(--destructive)',
  topRight: 'var(--destructive)',
}

const STATE_LABEL: Partial<Record<AssistantState['type'], string>> = {
  error: 'Oh no! an error occurred, try again later',
  halted: 'Oh, do you want me to do something else?',
  idle: 'Waiting for ya :p',
  ready: 'Ask me anything',
  thinking: 'Thinking',
  typing: 'Typing...',
}

const REDUCED_MOTION_VARIANTS = {
  animate: { opacity: 1 },
  exit: { opacity: 0 },
  initial: { opacity: 0 },
}

const FULL_MOTION_VARIANTS = {
  animate: { filter: 'blur(0px)', opacity: 1, y: 0 },
  exit: { filter: 'blur(2px)', opacity: 0, y: -5 },
  initial: { filter: 'blur(2px)', opacity: 0, y: 5 },
}

export type AssistantIndicatorProps = {
  state: AssistantState
}

export function AssistantIndicator({ state }: AssistantIndicatorProps) {
  const shouldReduceMotion = useReducedMotion()
  const isResting = state.type === 'idle' || state.type === 'ready'
  const isActive =
    state.type === 'thinking' ||
    state.type === 'active' ||
    state.type === 'typing'
  const isError = state.type === 'error'

  const quadrantColors = isResting
    ? RESTING_COLORS
    : isError
      ? ERROR_COLORS
      : undefined

  return (
    <div className="flex items-center gap-2">
      <GeneralMagicLogo
        animating={isActive && !shouldReduceMotion}
        className="size-3.5"
        quadrantColors={quadrantColors}
      />
      <AssistantIndicatorLabel state={state} />
    </div>
  )
}

const AssistantIndicatorLabel = ({ state }: { state: AssistantState }) => {
  const shouldReduceMotion = useReducedMotion()
  const isActive =
    state.type === 'thinking' ||
    state.type === 'active' ||
    state.type === 'typing'
  const isError = state.type === 'error'
  const label =
    state.type === 'active' ? state.label : (STATE_LABEL[state.type] ?? null)

  const variants = shouldReduceMotion
    ? REDUCED_MOTION_VARIANTS
    : FULL_MOTION_VARIANTS

  return (
    <AnimatePresence mode="wait">
      {label && (
        <motion.div
          animate={variants.animate}
          exit={variants.exit}
          initial={variants.initial}
          key={label}
          transition={{ duration: 0.2 }}
        >
          {isActive && !shouldReduceMotion ? (
            <ShimmeringText
              className="text-sm font-light"
              duration={1.2}
              spread={3}
              startOnView={false}
              text={label}
            />
          ) : (
            <span
              className={`text-sm font-light ${isError ? 'text-destructive' : 'text-muted-foreground'}`}
            >
              {label}
            </span>
          )}
        </motion.div>
      )}
    </AnimatePresence>
  )
}
