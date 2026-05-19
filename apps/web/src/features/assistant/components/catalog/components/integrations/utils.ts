import type { NormalizedToolCall } from '../../../../lib/agent-state'
import type { OpenPokeChatMessage } from '../../../../types'

const GOOGLE_NOT_CONNECTED_PATTERNS = [
  /gmail (is )?not (currently )?connected/i,
  /google (is )?not (currently )?connected/i,
  /no connected account/i,
  /no active connection/i,
  /ConnectedAccountNotFound/i,
  /connect your (gmail|google|googlesuper) account/i,
]

const matchesGoogleNotConnected = (text: string): boolean =>
  GOOGLE_NOT_CONNECTED_PATTERNS.some((re) => re.test(text))

const extractGoogleNotConnectedFromValue = (value: unknown): null | string => {
  if (typeof value === 'string') {
    return matchesGoogleNotConnected(value) ? value : null
  }
  if (value && typeof value === 'object') {
    const err = (value as { error?: unknown }).error
    if (typeof err === 'string' && matchesGoogleNotConnected(err)) return err
  }
  return null
}

export const getGoogleNotConnectedMessage = (
  call: NormalizedToolCall,
): null | string => {
  for (const candidate of [call.output, call.error]) {
    const match = extractGoogleNotConnectedFromValue(candidate)
    if (match) return match
  }
  return null
}

export const findGoogleNotConnectedTrigger = (
  message: OpenPokeChatMessage,
): null | { toolCallId: string } => {
  const parts = message.parts
  for (const part of parts) {
    const candidate = part as {
      data?: { event?: { error?: unknown; output?: unknown } }
      error?: unknown
      errorText?: unknown
      output?: unknown
      toolCallId?: unknown
      type?: unknown
    }
    const candidates: unknown[] = [
      candidate.output,
      candidate.error,
      candidate.errorText,
      candidate.data?.event?.output,
      candidate.data?.event?.error,
    ]
    for (const value of candidates) {
      if (!extractGoogleNotConnectedFromValue(value)) continue
      const toolCallId =
        typeof candidate.toolCallId === 'string'
          ? candidate.toolCallId
          : `integrations-trigger:${String(candidate.type ?? 'part')}`
      return { toolCallId }
    }
  }
  return null
}
