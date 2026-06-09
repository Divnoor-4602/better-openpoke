import type { Infer } from 'convex/values'

import { Table } from 'convex-helpers/server'
import { v } from 'convex/values'

import { User } from '../user/validators'

export const vMeetingStatus = v.union(
  v.literal('created'),
  v.literal('dispatching_listener'),
  v.literal('listener_joining'),
  v.literal('recording'),
  v.literal('ended'),
  v.literal('failed'),
)

export const vNotesStatus = v.union(
  v.literal('pending'),
  v.literal('generating'),
  v.literal('success'),
  v.literal('no_transcript'),
  v.literal('failed'),
)

export const vMeetingListenerProvider = v.union(v.literal('meetingbaas'))

export const vTranscriptionProvider = v.union(v.literal('assemblyai'))

export const vMeeting = v.object({
  botId: v.optional(v.string()),
  consentConfirmedAt: v.number(),
  consentText: v.string(),
  consentVersion: v.string(),
  createdAt: v.number(),
  endedAt: v.optional(v.number()),
  externalEventId: v.optional(v.string()),
  failedAt: v.optional(v.number()),
  failureReason: v.optional(v.string()),
  listenerProvider: vMeetingListenerProvider,
  mbCalendarId: v.optional(v.string()),
  meetingUrl: v.string(),
  notesError: v.optional(v.string()),
  notesGeneratedAt: v.optional(v.number()),
  notesStatus: v.optional(vNotesStatus),
  startedAt: v.optional(v.number()),
  status: vMeetingStatus,
  summary: v.optional(v.string()),
  title: v.optional(v.string()),
  transcriptionProvider: vTranscriptionProvider,
  transcriptionSessionId: v.optional(v.string()),
  updatedAt: v.number(),
  userId: User._id,
})

export const Meeting = Table('meetings', vMeeting.fields)

export type TMeeting = Infer<typeof Meeting.doc>
export type TMeetingId = Infer<typeof Meeting._id>
export type TMeetingListenerProvider = Infer<typeof vMeetingListenerProvider>
export type TMeetingStatus = Infer<typeof vMeetingStatus>
export type TNotesStatus = Infer<typeof vNotesStatus>
export type TTranscriptionProvider = Infer<typeof vTranscriptionProvider>
