import { Hono } from 'hono'
import { upgradeWebSocket, websocket } from 'hono/bun'

import type { AppDeps, AppEnv } from './context'

import { requireToken } from './auth/middleware'
import { health } from './routes/health'
import { sessions } from './routes/sessions'
import { webhookMeetingbaas } from './routes/webhook-meetingbaas'
import { wsMeetingHandler } from './routes/ws-meeting'

export function createApp(deps: AppDeps) {
  const app = new Hono<AppEnv>()
    .use('*', async (c, next) => {
      c.set('sessions', deps.sessions)
      await next()
    })
    .use('/sessions/*', requireToken)
    .route('/', health)
    .route('/', sessions)
    .route('/', webhookMeetingbaas)
    .get('/ws/meeting/:meetingId', upgradeWebSocket(wsMeetingHandler))

  return app
}

export { websocket }

export type AppType = ReturnType<typeof createApp>
