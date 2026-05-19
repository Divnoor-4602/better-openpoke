import type { MessageResource } from '@openpoke/sdk'

import type { OpenPokeChatMessage } from '@/features/assistant/types'

export function toUiMessages(items: MessageResource[]): OpenPokeChatMessage[] {
  const sorted = [...items].sort((a, b) => {
    const ai = a.turnIndex ?? 0
    const bi = b.turnIndex ?? 0
    if (ai !== bi) return ai - bi
    return a.createdAt.localeCompare(b.createdAt)
  })

  return sorted.map((message) => {
    const parts =
      message.parts && message.parts.length > 0
        ? message.parts
        : message.content
          ? [{ text: message.content, type: 'text' as const }]
          : []
    return {
      id: message.messageId,
      parts,
      role: message.role,
    } as OpenPokeChatMessage
  })
}
