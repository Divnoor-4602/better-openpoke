import { useChat } from '@ai-sdk/react'
import { openPokeDataPartSchemas, OpenPokeTransport } from '@openpoke/sdk'
import { useQueryClient } from '@tanstack/react-query'

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

export function ThreadDetailWidget({
  slots,
  threadId,
}: ThreadDetailWidgetProps) {
  const queryClient = useQueryClient()
  const messagesQuery = useThreadMessages(threadId)
  const initialMessages = toUiMessages(messagesQuery.data?.items ?? [])

  const transport = new OpenPokeTransport(poke, { threadId })

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
