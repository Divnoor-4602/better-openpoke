import { Hono } from 'hono'

import type { AppEnv } from '../context'

export const sessions = new Hono<AppEnv>()
  .get('/sessions/:meetingId', (c) => {
    const { meetingId } = c.req.param()
    const claims = c.var.claims!
    if (claims.meetingId !== meetingId) {
      return c.json({ error: 'meeting_mismatch' }, 403)
    }

    const session = c.var.sessions.get(meetingId)
    if (!session) {
      return c.json({
        meetingId,
        startedAt: null,
        state: 'idle' as const,
        utteranceCount: 0,
      })
    }

    return c.json({
      meetingId,
      startedAt: session.startedAt,
      state: session.state(),
      utteranceCount: session.utteranceCount(),
    })
  })
  .post('/sessions/:meetingId/terminate', async (c) => {
    const { meetingId } = c.req.param()
    const claims = c.var.claims!
    if (claims.meetingId !== meetingId) {
      return c.json({ error: 'meeting_mismatch' }, 403)
    }

    const session = c.var.sessions.get(meetingId)
    if (session) await session.terminate()

    return c.json({
      meetingId,
      ok: true as const,
      terminatedAt: Date.now(),
    })
  })
