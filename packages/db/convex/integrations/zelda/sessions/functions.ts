import type { ZeldaClient } from '../client'
import type {
  GetSessionByIdInput,
  GetSessionByIdOutput,
  TerminateSessionInput,
  TerminateSessionOutput,
} from './schema'

import { notFound, validationError } from '../../../error'
import { signListenerToken } from '../token'
import {
  GetSessionByIdInputSchema,
  GetSessionByIdOutputSchema,
  TerminateSessionInputSchema,
  TerminateSessionOutputSchema,
} from './schema'

export async function getSessionById(
  client: ZeldaClient,
  input: GetSessionByIdInput,
): Promise<GetSessionByIdOutput> {
  const args = GetSessionByIdInputSchema.parse(input)
  const token = await signListenerToken({
    meetingId: args.meetingId,
    userId: args.userId,
  })

  const res = await client.get(`/sessions/${args.meetingId}`, token)

  if (res.status === 404) {
    notFound({ entity: 'ZeldaSession', id: args.meetingId })
  }
  if (!res.ok) {
    validationError({
      entity: 'ZeldaSession',
      id: args.meetingId,
      message: `zelda getSessionById failed: ${res.status}`,
    })
  }

  const parsed = GetSessionByIdOutputSchema.safeParse(await res.json())
  if (!parsed.success) {
    validationError({
      entity: 'ZeldaSession',
      id: args.meetingId,
      message: `zelda getSessionById response invalid: ${parsed.error.message}`,
    })
  }
  return parsed.data
}

export async function terminateSession(
  client: ZeldaClient,
  input: TerminateSessionInput,
): Promise<TerminateSessionOutput> {
  const args = TerminateSessionInputSchema.parse(input)
  const token = await signListenerToken({
    meetingId: args.meetingId,
    userId: args.userId,
  })

  const res = await client.post(`/sessions/${args.meetingId}/terminate`, token)

  if (res.status === 404) {
    notFound({ entity: 'ZeldaSession', id: args.meetingId })
  }
  if (!res.ok) {
    validationError({
      entity: 'ZeldaSession',
      id: args.meetingId,
      message: `zelda terminateSession failed: ${res.status}`,
    })
  }

  const parsed = TerminateSessionOutputSchema.safeParse(await res.json())
  if (!parsed.success) {
    validationError({
      entity: 'ZeldaSession',
      id: args.meetingId,
      message: `zelda terminateSession response invalid: ${parsed.error.message}`,
    })
  }
  return parsed.data
}
