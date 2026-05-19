import { getAuthToken, resolveBaseUrl, subscribeAuthToken } from '@openpoke/sdk'
import { useEffect } from 'react'
import { toast } from 'sonner'

import { notify } from '@/lib/notifications'

type ReminderEvent = {
  fired_at: string
  payload: string
  trigger_id: number
}

const RECONNECT_MIN_MS = 2_000
const RECONNECT_MAX_MS = 30_000

export function useReminderNotifications(): void {
  useEffect(() => {
    const session = {
      aborted: false,
      backoff: RECONNECT_MIN_MS,
      controller: null as AbortController | null,
      // tracks the most-recent connect() so a token change can invalidate it.
      generation: 0,
      timer: null as null | ReturnType<typeof setTimeout>,
    }

    const deliverReminder = (event: ReminderEvent) => {
      const delivered = notify('Reminder', event.payload)
      if (!delivered) toast(event.payload)
    }

    const readStream = async (body: ReadableStream<Uint8Array>) => {
      const reader = body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      while (!session.aborted) {
        const { done, value } = await reader.read()
        if (done) return
        buffer += decoder.decode(value, { stream: true })
        const parts = buffer.split('\n\n')
        buffer = parts.pop() ?? ''
        for (const block of parts) {
          for (const line of block.split('\n')) {
            if (!line.startsWith('data:')) continue
            const json = line.slice(5).trim()
            if (!json) continue
            try {
              deliverReminder(JSON.parse(json) as ReminderEvent)
            } catch {
              // ignore malformed frames
            }
          }
        }
      }
    }

    const scheduleReconnect = (delay: number) => {
      if (session.aborted) return
      if (session.timer) clearTimeout(session.timer)
      session.timer = setTimeout(() => {
        session.timer = null
        void connect()
      }, delay)
    }

    const connect = async () => {
      if (session.aborted) return
      const myGeneration = ++session.generation
      const isCurrent = () =>
        !session.aborted && session.generation === myGeneration

      const token = getAuthToken()
      if (!token) {
        scheduleReconnect(session.backoff)
        session.backoff = Math.min(session.backoff * 2, RECONNECT_MAX_MS)
        return
      }

      const controller = new AbortController()
      session.controller = controller
      try {
        const response = await fetch(
          `${resolveBaseUrl()}/api/reminders/events`,
          {
            headers: {
              Accept: 'text/event-stream',
              Authorization: `Basic ${token}`,
            },
            signal: controller.signal,
          },
        )
        if (!response.ok || !response.body) {
          throw new Error(`reminder stream failed: ${response.status}`)
        }
        session.backoff = RECONNECT_MIN_MS
        await readStream(response.body)
      } catch (err) {
        if (err instanceof DOMException && err.name === 'AbortError') return
      } finally {
        if (session.controller === controller) session.controller = null
      }

      if (!isCurrent()) return
      scheduleReconnect(session.backoff)
      session.backoff = Math.min(session.backoff * 2, RECONNECT_MAX_MS)
    }

    void connect()
    const unsubscribeToken = subscribeAuthToken(() => {
      session.backoff = RECONNECT_MIN_MS
      session.controller?.abort()
      scheduleReconnect(0)
    })

    return () => {
      session.aborted = true
      unsubscribeToken()
      session.controller?.abort()
      if (session.timer) clearTimeout(session.timer)
    }
  }, [])
}
