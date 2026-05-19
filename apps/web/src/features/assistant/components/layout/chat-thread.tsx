import { useState } from 'react'
import { StickToBottom } from 'use-stick-to-bottom'

import { GeneralMagicLogo } from '@/assets/general-magic-logo'
import { MaxWidthWrapper } from '@/components/shared/max-width-wrapper'

import type { OpenPokeChatMessage } from '../../types'

import { ChatInput } from '../chat/chat-input'
import { MessageList } from '../message/message-list'
import { ScrollToLatestButton } from './scroll-to-latest-button'

export type ChatThreadSlots = {
  emptyStateFooter?: React.ReactNode
  integrationPrompt?: IntegrationPromptComponent
}

type ChatStatus = 'error' | 'ready' | 'streaming' | 'submitted'

type ChatThreadProps = {
  error?: Error
  messages: OpenPokeChatMessage[]
  onSend: (text: string) => Promise<void> | void
  onStop: () => void
  slots?: ChatThreadSlots
  status: ChatStatus
}

type IntegrationPromptComponent = React.ComponentType<{ message?: string }>

export const ChatThread = ({
  error,
  messages,
  onSend,
  onStop,
  slots,
  status,
}: ChatThreadProps) => {
  const [halted, setHalted] = useState<boolean>(false)
  const clearHalted = () => setHalted(false)

  const isStreaming = status === 'streaming' || status === 'submitted'

  const visibleError =
    error && error instanceof DOMException && error.name === 'AbortError'
      ? undefined
      : error

  const handleStop = () => {
    onStop()
    setHalted(true)
  }

  const handleSubmit = async (text: string) => {
    clearHalted()
    await onSend(text)
  }

  if (messages.length > 0) {
    return (
      <div className="flex flex-col h-dvh">
        <StickToBottom
          className="relative flex-1 min-h-0 [&>div]:scrollbar-thin [&>div]:[scrollbar-color:#e5e5e5_transparent]"
          initial="instant"
          resize="smooth"
        >
          <StickToBottom.Content className="pt-14 pb-20">
            <MaxWidthWrapper>
              <MessageList
                halted={halted}
                integrationPrompt={slots?.integrationPrompt}
                messages={messages}
                status={status}
              />
            </MaxWidthWrapper>
          </StickToBottom.Content>
          <ScrollToLatestButton />
        </StickToBottom>
        <MaxWidthWrapper className="px-4 pb-4 pt-2">
          <ChatInput
            isStreaming={isStreaming}
            onStop={handleStop}
            onSubmit={handleSubmit}
            onUserInput={clearHalted}
          />
        </MaxWidthWrapper>
      </div>
    )
  }

  return (
    <div className="h-dvh pt-14 flex flex-col">
      <MaxWidthWrapper className="flex flex-col flex-1 items-center justify-center pb-60">
        <div className="w-full flex flex-col gap-3">
          <div className="bg-muted pt-4 pb-0.5 rounded-xl flex-col gap-3 flex mt-40">
            <div className="flex items-center gap-2.5 px-3">
              <GeneralMagicLogo className="size-5 self-center" />
              <div className="font-heading text-base self-center">
                How can I help you today?
              </div>
            </div>
            <ChatInput
              isStreaming={isStreaming}
              onStop={handleStop}
              onSubmit={handleSubmit}
              onUserInput={clearHalted}
            />
          </div>
          {slots?.emptyStateFooter}
        </div>
        {visibleError && (
          <p className="text-xs text-destructive px-2 mt-1">
            {visibleError.message}
          </p>
        )}
      </MaxWidthWrapper>
    </div>
  )
}
