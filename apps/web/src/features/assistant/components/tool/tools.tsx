import { cn } from '@general-poke/ui'
import { motion, useReducedMotion } from 'motion/react'
import { useId, useState } from 'react'

import type { NormalizedToolCall } from '../../lib/agent-state'

import { summarizeTools } from '../../lib/tools-summary'
import { ToolPart } from './tool-part'
import { ToolsHeader } from './tools-header'

type ToolsProps = {
  calls: NormalizedToolCall[]
  wrapperClassName?: string
}

const containerVariants = {
  closed: { transition: { staggerChildren: 0 } },
  open: { transition: { delayChildren: 0.03, staggerChildren: 0.015 } },
}

const itemVariants = {
  closed: { opacity: 0, transition: { duration: 0.12 } },
  open: { opacity: 1, transition: { duration: 0.18 } },
}

export const Tools = ({ calls, wrapperClassName }: ToolsProps) => {
  const [open, setOpen] = useState<boolean>(false)
  const prefersReducedMotion = useReducedMotion()
  const summary = summarizeTools(calls)
  const panelId = useId()

  if (calls.length === 0) return null

  return (
    <motion.div
      animate={{ opacity: 1, y: 0 }}
      className={cn('flex flex-col gap-1', wrapperClassName)}
      initial={{ opacity: 0, y: 2 }}
      transition={{ duration: 0.15, ease: 'easeOut' }}
    >
      <ToolsHeader
        onToggle={() => setOpen((v) => !v)}
        open={open}
        panelId={panelId}
        summary={summary}
      />
      <div
        className={cn(
          'grid transition-[grid-template-rows] duration-200 ease-out',
          open ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]',
        )}
        id={panelId}
      >
        <div className="overflow-hidden min-h-0">
          <motion.div
            animate={open ? 'open' : 'closed'}
            className="flex pt-2"
            initial={false}
            variants={containerVariants}
          >
            <div className="w-px shrink-0 self-stretch bg-border ml-1.5" />
            <div className="flex flex-col gap-2 pl-3.5 flex-1">
              {calls.map((call) => (
                <motion.div
                  key={call.toolCallId}
                  variants={prefersReducedMotion ? undefined : itemVariants}
                >
                  <ToolPart call={call} />
                </motion.div>
              ))}
            </div>
          </motion.div>
        </div>
      </div>
    </motion.div>
  )
}
