import { useState } from 'react'

import type { AssistantState } from '../../lib/agent-state'
import type { OpenPokeChatMessage } from '../../types'

import { buildMessageBlocks, getAssistantText } from '../../lib/agent-state'
import { readCreatedAt } from '../../lib/format-time'
import { AssistantMessage } from './assistant-message'
import { UserMessage } from './user-message'

type MessageProps = {
  assistantState?: AssistantState
  integrationPrompt?: React.ComponentType<{ message?: string }>
  message: OpenPokeChatMessage
}

const ASSISTANT_IN_FLIGHT: ReadonlySet<AssistantState['type']> = new Set([
  'active',
  'thinking',
  'typing',
])

export const Message = ({
  assistantState,
  integrationPrompt,
  message,
}: MessageProps) => {
  const [createdAt] = useState<number>(() => readCreatedAt(message))

  if (message.role === 'user') {
    const text = getAssistantText(message)
    if (!text) return null
    return <UserMessage createdAt={createdAt} text={text} />
  }

  const isStreaming =
    assistantState !== undefined && ASSISTANT_IN_FLIGHT.has(assistantState.type)
  const blocks = buildMessageBlocks(message, {
    suppressIntegrationsButton: isStreaming,
  })

  return (
    <AssistantMessage
      assistantState={assistantState}
      blocks={blocks}
      createdAt={createdAt}
      integrationPrompt={integrationPrompt}
      isStreaming={isStreaming}
    />
  )
}
