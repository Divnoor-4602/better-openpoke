import { jwtVerify } from 'jose'

import type { ListenerTokenClaims } from '../types'

const ISSUER = 'convex'
const AUDIENCE = 'zelda'
const SCOPE = 'zelda-listener' as const

function getSecret(): Uint8Array {
  const secret = process.env.ZELDA_JWT_SECRET
  if (!secret) throw new Error('ZELDA_JWT_SECRET is not set')
  return new TextEncoder().encode(secret)
}

export async function verifyListenerToken(
  token: string,
): Promise<ListenerTokenClaims> {
  const { payload } = await jwtVerify(token, getSecret(), {
    audience: AUDIENCE,
    issuer: ISSUER,
  })

  const { meetingId, scope, sub } = payload as {
    meetingId?: unknown
    scope?: unknown
    sub?: unknown
  }

  if (
    typeof meetingId !== 'string' ||
    typeof sub !== 'string' ||
    scope !== SCOPE
  ) {
    throw new Error('Token claims malformed')
  }

  return { meetingId, scope: SCOPE, userId: sub }
}
