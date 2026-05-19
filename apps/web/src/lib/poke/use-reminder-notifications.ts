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

/**
 * Subscribes once (per mount) to the workspace's reminder fire stream.
 *
 * `EventSource` can't send Authorization headers, so we hand-roll the SSE
 * read on top of `fetch`. The connection stays alive while the tab is
 * open; on disconnect it reconnects with exponential backoff.
 */
export function useReminderNotifications(): void {
  useEffect(() => {
    let aborted = false
    let controller: AbortController | null = null
    let timer: null | ReturnType<typeof setTimeout> = null
    let backoff = RECONNECT_MIN_MS

    const deliverReminder = (event: ReminderEvent) => {
      const delivered = notify('Reminder', event.payload)
      if (!delivered) toast(event.payload)
    }

    const readStream = async (body: ReadableStream<Uint8Array>) => {
      const reader = body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      while (!aborted) {
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

    const scheduleReconnect = () => {
      if (aborted) return
      timer = setTimeout(() => void connect(), backoff)
      backoff = Math.min(backoff * 2, RECONNECT_MAX_MS)
    }

    const connect = async () => {
      if (aborted) return
      const token = getAuthToken()
      if (!token) {
        scheduleReconnect()
        return
      }

      controller = new AbortController()
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
        backoff = RECONNECT_MIN_MS
        await readStream(response.body)
      } catch (err) {
        // `aborted` flips inside the cleanup closure; the narrowing is
        // wrong here.
        // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition
        if (aborted) return
        if (err instanceof DOMException && err.name === 'AbortError') return
      }
      scheduleReconnect()
    }

    void connect()
    const unsubscribeToken = subscribeAuthToken(() => {
      // token changed (login/logout) — drop the current stream so the next
      // connect picks up the new credentials.
      controller?.abort()
    })

    return () => {
      aborted = true
      unsubscribeToken()
      controller?.abort()
      if (timer) clearTimeout(timer)
    }
  }, [])
}
