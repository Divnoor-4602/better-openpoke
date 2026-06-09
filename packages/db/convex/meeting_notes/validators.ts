import type { Infer } from 'convex/values'

import { Table } from 'convex-helpers/server'
import { v } from 'convex/values'

import { Meeting } from '../meeting/validators'
import { User } from '../user/validators'

export const vMeetingNotes = v.object({
  content: v.string(),
  generatedAt: v.number(),
  meetingId: Meeting._id,
  title: v.string(),
  updatedAt: v.number(),
  userId: User._id,
})

export const MeetingNotes = Table('meetingNotes', vMeetingNotes.fields)

export type TMeetingNotes = Infer<typeof MeetingNotes.doc>
export type TMeetingNotesId = Infer<typeof MeetingNotes._id>
