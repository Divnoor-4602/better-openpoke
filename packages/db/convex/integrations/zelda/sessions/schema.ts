import { zid } from 'convex-helpers/server/zod4'
import { z } from 'zod'

export const SessionStateSchema = z.enum([
  'idle',
  'connecting',
  'streaming',
  'closed',
])
export type SessionState = z.infer<typeof SessionStateSchema>

export const GetSessionByIdInputSchema = z.object({
  meetingId: zid('meetings'),
  userId: zid('users'),
})
export type GetSessionByIdInput = z.infer<typeof GetSessionByIdInputSchema>

export const GetSessionByIdOutputSchema = z.object({
  meetingId: zid('meetings'),
  startedAt: z.number().nullable(),
  state: SessionStateSchema,
  utteranceCount: z.number(),
})
export type GetSessionByIdOutput = z.infer<typeof GetSessionByIdOutputSchema>

export const TerminateSessionInputSchema = z.object({
  meetingId: zid('meetings'),
  userId: zid('users'),
})
export type TerminateSessionInput = z.infer<typeof TerminateSessionInputSchema>

export const TerminateSessionOutputSchema = z.object({
  meetingId: zid('meetings'),
  ok: z.literal(true),
  terminatedAt: z.number(),
})
export type TerminateSessionOutput = z.infer<
  typeof TerminateSessionOutputSchema
>
