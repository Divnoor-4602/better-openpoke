import { useRef } from 'react'

import { requestNotificationPermissionIfDefault } from '@/lib/notifications'
import { cn } from '@/lib/utils'

import { useChatDraftStore } from '../../store/chat-draft-store'
import { AttachmentsButton } from './attachments-button'
import { SendButton } from './send-button'

type ChatInputProps = {
  className?: string
  disabled?: boolean
  isStreaming?: boolean
  onStop?: () => void
  onSubmit: (text: string) => void
  onUserInput?: () => void
}

export const ChatInput = ({
  className,
  disabled,
  isStreaming,
  onStop,
  onSubmit,
  onUserInput,
}: ChatInputProps) => {
  const value = useChatDraftStore((s) => s.text)
  const setValue = useChatDraftStore((s) => s.setText)
  const textareaRef = useRef<HTMLTextAreaElement | null>(null)

  const handleSubmit = () => {
    const text = value.trim()
    if (!text) return
    requestNotificationPermissionIfDefault()
    setValue('')
    if (isStreaming && onStop) onStop()
    onSubmit(text)
  }

  const hasText = value.trim().length > 0

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  return (
    <div
      className={cn(
        'border bg-white relative flex w-full cursor-text flex-col overflow-hidden rounded-poke p-3',
        className,
      )}
    >
      <div
        className="text-text-primary relative flex w-full flex-1 flex-col overflow-y-auto pt-1 px-1 text-sm pb-2"
        style={{
          height: 'auto',
          maxHeight: 'max(250px, 20vh)',
          minHeight: '80px',
          scrollbarWidth: 'thin',
        }}
      >
        <textarea
          aria-label="Message"
          className="text-text-primary placeholder:text-text-secondary w-full min-h-19.5 resize-none rounded-none bg-transparent text-sm outline-none focus:outline-none"
          disabled={disabled}
          onChange={(e) => {
            setValue(e.target.value)
            onUserInput?.()
          }}
          onKeyDown={handleKeyDown}
          placeholder="Ask me to draft, email, schedule, remind, or follow up"
          ref={textareaRef}
          value={value}
        />
      </div>
      <div className="flex items-center justify-between">
        <AttachmentsButton />
        <SendButton
          disabled={disabled || !hasText}
          hasText={hasText}
          isStreaming={isStreaming}
          onClick={handleSubmit}
          onStop={onStop}
        />
      </div>
    </div>
  )
}
