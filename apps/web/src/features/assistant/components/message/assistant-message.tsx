import { Streamdown } from 'streamdown'

import type { AssistantState, MessageBlock } from '../../lib/agent-state'

import { formatClock } from '../../lib/format-time'
import { CatalogRenderer } from '../catalog/renderer'
import { Tools } from '../tool/tools'
import { AssistantIndicator } from './assistant-indicator'
import { STREAMDOWN_COMPONENTS } from './streamdown'

type AssistantMessageProps = {
  assistantState?: AssistantState
  blocks: MessageBlock[]
  createdAt: number
  integrationPrompt?: React.ComponentType<{ message?: string }>
  isStreaming?: boolean
}

const IN_FLIGHT_STATES: ReadonlySet<AssistantState['type']> = new Set([
  'active',
  'thinking',
  'typing',
])

export const AssistantMessage = ({
  assistantState,
  blocks,
  createdAt,
  integrationPrompt,
  isStreaming = false,
}: AssistantMessageProps) => {
  const indicator = assistantState ? (
    <AssistantIndicator state={assistantState} />
  ) : null
  const isDone = !assistantState || !IN_FLIGHT_STATES.has(assistantState.type)

  return (
    <div className="group flex flex-col gap-2">
      {blocks.map((block) => {
        if (block.type === 'text') {
          return (
            <Streamdown
              animated
              className="prose prose-sm  max-w-none text-sm leading-relaxed"
              components={STREAMDOWN_COMPONENTS}
              isAnimating={isStreaming}
              key={block.id}
              linkSafety={{ enabled: false }}
            >
              {block.text}
            </Streamdown>
          )
        }
        if (block.type === 'catalog') {
          return (
            <CatalogRenderer
              block={block}
              integrationPrompt={integrationPrompt}
              key={block.id}
            />
          )
        }
        return (
          <Tools calls={block.calls} key={block.id} wrapperClassName="my-2" />
        )
      })}

      {indicator && <div className="mt-5">{indicator}</div>}
      {isDone && (
        <time className="text-xs tabular-nums text-muted-foreground/70 mt-2 opacity-0 transition-opacity duration-150 group-hover:opacity-100">
          {formatClock(createdAt)}
        </time>
      )}
    </div>
  )
}
