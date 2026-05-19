import { useChat } from '@ai-sdk/react'
import { openPokeDataPartSchemas, OpenPokeTransport } from '@openpoke/sdk'
import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import type { ChatThreadSlots } from '@/features/assistant/components/layout/chat-thread'
import type { OpenPokeChatMessage } from '@/features/assistant/types'

import { ChatThread } from '@/features/assistant/components/layout/chat-thread'
import { poke } from '@/lib/poke/client'
import { useGoogleSync } from '@/lib/poke/google-sync/use-google-sync'
import { threadKeys, useThreadMessages } from '@/lib/poke/thread'

import { toUiMessages } from '../lib/to-ui-messages'

type ThreadDetailWidgetProps = {
  slots?: ChatThreadSlots
  threadId: string
}

// Stable empty fallback so `useChat` doesn't see a new array identity on every
// render of the loading state.
const NO_INITIAL_MESSAGES: OpenPokeChatMessage[] = []

export function ThreadDetailWidget({
  slots,
  threadId,
}: ThreadDetailWidgetProps) {
  const queryClient = useQueryClient()
  const messagesQuery = useThreadMessages(threadId)
  const items = messagesQuery.data?.items
  const initialMessages = items ? toUiMessages(items) : NO_INITIAL_MESSAGES

  // Transport must be referentially stable for the chat session — re-creating
  // it on every render would re-init `useChat` and drop in-flight streams.
  // `useState`'s lazy initializer pins it for the lifetime of this threadId.
  const [transport] = useState(() => new OpenPokeTransport(poke, { threadId }))

  const { error, messages, sendMessage, status, stop } =
    useChat<OpenPokeChatMessage>({
      dataPartSchemas: openPokeDataPartSchemas,
      messages: initialMessages,
      onFinish: () => {
        void queryClient.invalidateQueries({
          queryKey: threadKeys.detail(threadId),
        })
        void queryClient.invalidateQueries({ queryKey: threadKeys.lists() })
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
