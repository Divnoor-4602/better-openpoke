import { CaretDownIcon, CaretRightIcon } from '@phosphor-icons/react'
import { useId, useState } from 'react'

type ReasoningPartProps = {
  state: 'done' | 'streaming'
  text: string
}

export const ReasoningPart = ({ state, text }: ReasoningPartProps) => {
  const [expanded, setExpanded] = useState(false)
  const panelId = useId()

  if (state === 'streaming') {
    return (
      <div className="flex items-center gap-1.5 text-xs text-muted-foreground py-1">
        <span className="size-1.5 rounded-full bg-muted-foreground/50 animate-pulse" />
        Thinking…
      </div>
    )
  }

  return (
    <div className="text-xs text-muted-foreground">
      <button
        aria-controls={panelId}
        aria-expanded={expanded}
        className="flex items-center gap-1 hover:text-foreground transition-colors py-1"
        onClick={() => setExpanded((v) => !v)}
        type="button"
      >
        {expanded ? (
          <CaretDownIcon className="size-3" />
        ) : (
          <CaretRightIcon className="size-3" />
        )}
        Reasoning
      </button>
      {expanded && (
        <p
          className="mt-1 whitespace-pre-wrap leading-relaxed border-l-2 border-muted-foreground/20 pl-2.5"
          id={panelId}
        >
          {text}
        </p>
      )}
    </div>
  )
}
