import { hc } from 'hono/client'

import type { AppType } from './app'

export function createZeldaClient(baseUrl: string, token: string) {
  return hc<AppType>(baseUrl, {
    headers: { authorization: `Bearer ${token}` },
  })
}

export type ZeldaClient = ReturnType<typeof createZeldaClient>
