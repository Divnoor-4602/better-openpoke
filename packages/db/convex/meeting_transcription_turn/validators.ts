import type { Infer } from 'convex/values'

import { Table } from 'convex-helpers/server'
import { v } from 'convex/values'

import { Meeting } from '../meeting/validators'
import { User } from '../user/validators'

export const vMeetingTranscriptTurn = v.object({
  createdAt: v.number(),
  endMs: v.optional(v.number()),
  meetingId: Meeting._id,
  speakerLabel: v.optional(v.string()),
  startMs: v.optional(v.number()),
  text: v.string(),
  turnOrder: v.number(),
  userId: User._id,
})

export const MeetingTranscriptTurn = Table(
  'meetingTranscriptTurns',
  vMeetingTranscriptTurn.fields,
)

export type TMeetingTranscriptTurn = Infer<typeof MeetingTranscriptTurn.doc>
export type TMeetingTranscriptTurnId = Infer<typeof MeetingTranscriptTurn._id>
