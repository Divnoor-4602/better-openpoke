import {
  CheckCircleIcon,
  ProhibitIcon,
  SpinnerIcon,
  XCircleIcon,
} from '@phosphor-icons/react'
import { motion } from 'motion/react'

import { ShimmeringText } from '@general-poke/ui/components/shimmering-text'
import { cn } from '@/lib/utils'

import type { NormalizedToolCall } from '../../lib/agent-state'

import { isToolCallInFlight } from '../../lib/agent-state'
import { getToolLabel, getToolMeta } from '../../lib/tool-registry'

type ToolPartProps = {
  call: NormalizedToolCall
}

export const ToolPart = ({ call }: ToolPartProps) => {
  const meta = getToolMeta(call.toolName)
  const { actionIcon: ActionIcon, primaryIcon: PrimaryIcon } = meta
  const label = getToolLabel(meta, call.state)

  const inFlight = isToolCallInFlight(call)
  const isError = call.state === 'error' || call.state === 'cancel'

  return (
    <motion.div
      animate={{ opacity: 1 }}
      className="flex items-center justify-between pr-0.5"
      initial={{ opacity: 0 }}
    >
      <div className="flex items-center gap-2">
        <div className="flex items-center">
          <div className="rounded-full p-1 border bg-white">
            {PrimaryIcon ? <PrimaryIcon className="size-2.5 shrink-0" /> : null}
          </div>
          <div className="rounded-full p-1 border bg-white -ml-1.5">
            {ActionIcon ? <ActionIcon className="size-2.5 shrink-0" /> : null}
          </div>
        </div>

        {inFlight ? (
          <ShimmeringText
            className="text-13"
            duration={1.6}
            repeatDelay={0.2}
            repeatType="reverse"
            shimmerColor="var(--foreground)"
            spread={3}
            startOnView={false}
            text={label}
          />
        ) : (
          <span
            className={cn(
              'text-13',
              isError ? 'text-destructive' : 'text-muted-foreground',
            )}
          >
            {label}
          </span>
        )}
      </div>

      <StateIndicator state={call.state} />
    </motion.div>
  )
}

const StateIndicator = ({ state }: { state: NormalizedToolCall['state'] }) => {
  if (state === 'start' || state === 'running') {
    return (
      <SpinnerIcon className="size-3.5 shrink-0 animate-spin text-muted-foreground" />
    )
  }
  if (state === 'success') {
    return <CheckCircleIcon className="size-3.5 shrink-0 text-green-600" />
  }
  if (state === 'cancel') {
    return <ProhibitIcon className="size-3.5 shrink-0 text-destructive" />
  }
  return <XCircleIcon className="size-3.5 shrink-0 text-destructive" />
}
