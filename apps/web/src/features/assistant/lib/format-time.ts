import { format, intervalToDuration } from 'date-fns'

import type { OpenPokeChatMessage } from '../types'

// "5s", "1m 12s", "1h 3m" — compact elapsed string for durations.
export const formatElapsed = (ms: number): string => {
  const safe = Math.max(0, Math.round(ms))
  const d = intervalToDuration({ end: safe, start: 0 })
  if (d.hours) return `${d.hours}h ${d.minutes ?? 0}m`
  if (d.minutes) return `${d.minutes}m ${d.seconds ?? 0}s`
  return `${d.seconds ?? 0}s`
}

// "8:33" — clock time for a completed event.
export const formatClock = (ms: number): string => format(new Date(ms), 'h:mm')

// Reads server-provided message timestamp from metadata, falls back to now.
export const readCreatedAt = (message: OpenPokeChatMessage): number => {
  const meta = message.metadata
  if (typeof meta === 'object' && meta !== null) {
    const candidate = (meta as { createdAt?: unknown }).createdAt
    if (typeof candidate === 'number') return candidate
    if (typeof candidate === 'string') {
      const ms = Date.parse(candidate)
      if (!Number.isNaN(ms)) return ms
    }
    if (candidate instanceof Date) return candidate.getTime()
  }
  return Date.now()
}
