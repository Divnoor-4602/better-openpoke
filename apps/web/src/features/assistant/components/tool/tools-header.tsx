import { CaretRightIcon } from '@phosphor-icons/react'
import { AnimatePresence, motion } from 'motion/react'

import { ShimmeringText } from '@general-poke/ui/components/shimmering-text'
import { cn } from '@/lib/utils'

import type { ToolsSummary } from '../../lib/tools-summary'

import { useTimingLabel } from '../../hooks/use-timing-label'
import { CATEGORY_BRAND_ICONS } from '../../lib/tool-registry'

type ToolsHeaderProps = {
  onToggle: () => void
  open: boolean
  panelId: string
  summary: ToolsSummary
}

export const ToolsHeader = ({
  onToggle,
  open,
  panelId,
  summary,
}: ToolsHeaderProps) => {
  const { categories, completedAt, isRunning, startedAt } = summary
  const trailing = useTimingLabel({ completedAt, isRunning, startedAt })
  const label = isRunning
    ? trailing
      ? `Working ${trailing}`
      : 'Working'
    : trailing
      ? `Worked for ${trailing}`
      : 'Actions'

  return (
    <button
      aria-controls={panelId}
      aria-expanded={open}
      className="flex items-center justify-between w-full text-left cursor-pointer"
      onClick={onToggle}
      type="button"
    >
      <div className="flex items-center gap-2">
        <CaretRightIcon
          className={cn(
            'size-3 text-muted-foreground transition-transform duration-150',
            open && 'rotate-90',
          )}
        />
        {isRunning ? (
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
          <span className="text-13 font-normal text-muted-foreground">
            {label}
          </span>
        )}
      </div>
      <div className="flex items-center -space-x-1">
        <AnimatePresence initial={false}>
          {categories.map((cat) => {
            const Icon = CATEGORY_BRAND_ICONS[cat]
            if (!Icon) return null
            return (
              <motion.div
                animate={{ filter: 'none', opacity: 1, scale: 1 }}
                className="rounded-full p-1 border bg-white"
                exit={{ filter: 'blur(2px)', opacity: 0, scale: 0.6 }}
                initial={{ filter: 'blur(2px)', opacity: 0, scale: 0.6 }}
                key={cat}
                transition={{ duration: 0.18, ease: 'easeOut' }}
              >
                <Icon className="size-2.5" />
              </motion.div>
            )
          })}
        </AnimatePresence>
      </div>
    </button>
  )
}
