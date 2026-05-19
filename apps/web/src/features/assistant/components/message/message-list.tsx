import type { AssistantState } from '../../lib/agent-state'
import type { OpenPokeChatMessage } from '../../types'

import { useAssistantState } from '../../hooks/use-assistant-state'
import { AssistantIndicator } from './assistant-indicator'
import { Message } from './message'

type ChatStatus = Parameters<typeof useAssistantState>[0]

type MessageListProps = {
  halted?: boolean
  integrationPrompt?: React.ComponentType<{ message?: string }>
  messages: OpenPokeChatMessage[]
  status: ChatStatus
}

const IN_FLIGHT_STATES: ReadonlySet<AssistantState['type']> = new Set([
  'active',
  'thinking',
  'typing',
])

export const MessageList = ({
  halted,
  integrationPrompt,
  messages,
  status,
}: MessageListProps) => {
  const assistantState = useAssistantState(status, messages, halted)
  const lastAssistantIdx = messages.findLastIndex((m) => m.role === 'assistant')
  const lastAssistantIsTail = lastAssistantIdx === messages.length - 1
  const showPendingIndicator =
    IN_FLIGHT_STATES.has(assistantState.type) && !lastAssistantIsTail

  return (
    <div className="@container/thread px-6 py-4 flex flex-col">
      {messages.map((message, i) => {
        const prevRole = messages[i - 1]?.role
        const isNewExchange = i > 0 && prevRole !== message.role
        const isLastAssistant =
          message.role === 'assistant' && i === lastAssistantIdx
        return (
          <div
            className={isNewExchange ? 'mt-6' : i > 0 ? 'mt-2' : ''}
            key={message.id}
          >
            <Message
              assistantState={
                isLastAssistant && lastAssistantIsTail
                  ? assistantState
                  : undefined
              }
              integrationPrompt={integrationPrompt}
              message={message}
            />
          </div>
        )
      })}
      {showPendingIndicator && (
        <div className="mt-6">
          <AssistantIndicator state={assistantState} />
        </div>
      )}
    </div>
  )
}
