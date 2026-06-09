import { Hono } from 'hono'

import type { AppEnv } from '../context'

type WebhookEvent = {
  data?: {
    bot_id?: string
    code?: string
    error?: string
    error_type?: string
    meeting_id?: string
    message?: string
    sub_code?: string
  }
  event?: string
}

export const webhookMeetingbaas = new Hono<AppEnv>().post(
  '/webhooks/meetingbaas',
  async (c) => {
    const expected = process.env.MEETINGBAAS_WEBHOOK_SECRET
    if (!expected) {
      console.error('[mb-webhook] MEETINGBAAS_WEBHOOK_SECRET not set')
      return c.json({ error: 'server_misconfigured' }, 500)
    }
    if (c.req.header('x-mb-secret') !== expected) {
      return c.json({ error: 'invalid_secret' }, 401)
    }

    const body = (await c.req.json().catch(() => null)) as WebhookEvent | null
    if (!body) return c.json({ error: 'invalid_json' }, 400)

    const meetingId = body.data?.meeting_id ?? null
    console.log('[mb-webhook]', body.event, {
      botId: body.data?.bot_id ?? null,
      code: body.data?.code ?? null,
      error: body.data?.error ?? null,
      errorType: body.data?.error_type ?? null,
      meetingId,
      message: body.data?.message ?? null,
      subCode: body.data?.sub_code ?? null,
    })

    if (body.event === 'bot.left' || body.event === 'bot.error') {
      const session = meetingId ? c.var.sessions.get(meetingId) : undefined
      if (session) await session.terminate()
    }

    return c.json({ ok: true })
  },
)
