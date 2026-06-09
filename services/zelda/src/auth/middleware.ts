import { createMiddleware } from 'hono/factory'

import type { AppEnv } from '../context'

import { verifyListenerToken } from './verify-token'

export const requireToken = createMiddleware<AppEnv>(async (c, next) => {
  const header = c.req.header('authorization')
  const queryToken = c.req.query('token')
  const raw = header?.startsWith('Bearer ') ? header.slice(7) : queryToken

  if (!raw) return c.json({ error: 'missing_token' }, 401)

  try {
    const claims = await verifyListenerToken(raw)
    c.set('claims', claims)
    await next()
  } catch {
    return c.json({ error: 'invalid_token' }, 401)
  }
})
