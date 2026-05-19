import { useChat } from '@ai-sdk/react'
import { openPokeDataPartSchemas, OpenPokeTransport } from '@openpoke/sdk'
import { useQueryClient } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import { useState } from 'react'

import type { ChatThreadSlots } from '@/features/assistant/components/layout/chat-thread'
import type { OpenPokeChatMessage } from '@/features/assistant/types'

import { ChatThread } from '@/features/assistant/components/layout/chat-thread'
import { poke } from '@/lib/poke/client'
import { useGoogleSync } from '@/lib/poke/google-sync/use-google-sync'
import { threadKeys } from '@/lib/poke/thread'

type NewThreadWidgetProps = {
  slots?: ChatThreadSlots
}

export function NewThreadWidget({ slots }: NewThreadWidgetProps) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  // Pin the transport for this widget's lifetime; re-creating it would reset
  // `useChat` and lose the in-flight thread assignment.
  const [transport] = useState(() => new OpenPokeTransport(poke))

  const { error, messages, sendMessage, status, stop } =
    useChat<OpenPokeChatMessage>({
      dataPartSchemas: openPokeDataPartSchemas,
      onFinish: () => {
        void queryClient.invalidateQueries({ queryKey: threadKeys.lists() })
        const threadId = transport.getThreadId()
        if (threadId) {
          void navigate({
            params: { threadId },
            replace: true,
            to: '/threads/$threadId',
          })
        }
      },
      transport,
    })

  useGoogleSync(messages)

  return (
    <ChatThread
      error={error ?? undefined}
      messages={messages}
      onSend={(text) => sendMessage({ text })}
      onStop={stop}
      slots={slots}
      status={status}
    />
  )
}
