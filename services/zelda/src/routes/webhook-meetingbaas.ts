import { Hono } from 'hono'

import type { AppEnv } from '../context'

type WebhookEvent = {
  data?: {
    bot_id?: string
    meeting_id?: string
  }
  event?: string
}

export const webhookMeetingbaas = new Hono<AppEnv>().post(
  '/webhooks/meetingbaas',
  async (c) => {
    // TODO: HMAC signature verification once MeetingBaas signing scheme is wired.
    const body = (await c.req.json().catch(() => null)) as WebhookEvent | null
    if (!body) return c.json({ error: 'invalid_json' }, 400)

    const meetingId = body.data?.meeting_id ?? null
    console.log('[mb-webhook]', body.event, { meetingId })

    if (body.event === 'bot.left' || body.event === 'bot.error') {
      const session = meetingId ? c.var.sessions.get(meetingId) : undefined
      if (session) await session.terminate()
    }

    return c.json({ ok: true })
  },
)
