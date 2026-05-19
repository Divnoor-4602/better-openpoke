import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef } from 'react'

import type { OpenPokeChatMessage } from '@/features/assistant/types'

import { getNormalizedToolCalls } from '@/features/assistant/lib/agent-state'

import { GOOGLE_SYNC_REGISTRY } from './registry'

export function useGoogleSync(messages: OpenPokeChatMessage[]) {
  const queryClient = useQueryClient()
  const seenRef = useRef<Set<string>>(new Set<string>())

  useEffect(() => {
    for (const message of messages) {
      for (const call of getNormalizedToolCalls(message)) {
        if (call.state !== 'success') continue
        if (seenRef.current.has(call.toolCallId)) continue
        const entry = GOOGLE_SYNC_REGISTRY[call.toolName]
        if (!entry) continue

        const key = entry.keyFn(call.input)
        if (!key) {
          seenRef.current.add(call.toolCallId)
          continue
        }
        const patch = entry.patch(call.input, call.output)

        queryClient.setQueryData(key, (current: unknown) => ({
          ...(current && typeof current === 'object'
            ? (current as Record<string, unknown>)
            : {}),
          ...patch,
        }))
        seenRef.current.add(call.toolCallId)
      }
    }
  }, [messages, queryClient])
}
