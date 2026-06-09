import { jwtVerify, SignJWT } from 'jose'

import type { TMeetingId } from '../../meeting/validators'
import type { TUserId } from '../../user/validators'

import { validationError } from '../../error'

const ISSUER = 'convex'
const AUDIENCE = 'zelda'
const SCOPE = 'zelda-listener'
const TTL_SECONDS = 11_100

export type ListenerTokenClaims = {
  meetingId: TMeetingId
  scope: typeof SCOPE
  userId: TUserId
}

export async function signListenerToken(args: {
  meetingId: TMeetingId
  userId: TUserId
}): Promise<string> {
  return await new SignJWT({ meetingId: args.meetingId, scope: SCOPE })
    .setProtectedHeader({ alg: 'HS256', typ: 'JWT' })
    .setIssuer(ISSUER)
    .setAudience(AUDIENCE)
    .setSubject(args.userId)
    .setIssuedAt()
    .setExpirationTime(`${TTL_SECONDS}s`)
    .sign(getSecret())
}

export async function verifyListenerToken(
  token: string,
): Promise<ListenerTokenClaims> {
  const { payload } = await jwtVerify(token, getSecret(), {
    audience: AUDIENCE,
    issuer: ISSUER,
  }).catch(() => {
    validationError({
      entity: 'ZeldaToken',
      message: 'Invalid or expired token',
    })
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
    validationError({
      entity: 'ZeldaToken',
      message: 'Token claims malformed',
    })
  }

  return {
    meetingId: meetingId as TMeetingId,
    scope: SCOPE,
    userId: sub as TUserId,
  }
}

function getSecret(): Uint8Array {
  const secret = process.env.ZELDA_JWT_SECRET
  if (!secret) {
    validationError({
      entity: 'ZeldaToken',
      message: 'ZELDA_JWT_SECRET is not set',
    })
  }
  return new TextEncoder().encode(secret)
}
