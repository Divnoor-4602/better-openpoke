import type { Infer } from 'convex/values'

import { Table } from 'convex-helpers/server'
import { v } from 'convex/values'

import { CalendarConnection } from '../calendar_connection/validators'
import { User } from '../user/validators'

export const vCalendarEventStatus = v.union(
  v.literal('confirmed'),
  v.literal('cancelled'),
  v.literal('tentative'),
)

export const vCalendarMeetingPlatform = v.union(
  v.literal('zoom'),
  v.literal('meet'),
  v.literal('teams'),
)

export const vCalendarEvent = v.object({
  botScheduled: v.boolean(),
  calendarConnectionId: CalendarConnection._id,
  endTime: v.number(),
  eventId: v.string(),
  isException: v.boolean(),
  mbCalendarId: v.string(),
  meetingPlatform: v.union(vCalendarMeetingPlatform, v.null()),
  meetingUrl: v.union(v.string(), v.null()),
  seriesId: v.string(),
  startTime: v.number(),
  status: vCalendarEventStatus,
  title: v.string(),
  updatedAt: v.number(),
  userId: User._id,
})

export const CalendarEvent = Table('calendarEvents', vCalendarEvent.fields)

export type TCalendarEvent = Infer<typeof CalendarEvent.doc>
export type TCalendarEventId = Infer<typeof CalendarEvent._id>
export type TCalendarEventStatus = Infer<typeof vCalendarEventStatus>
export type TCalendarMeetingPlatform = Infer<typeof vCalendarMeetingPlatform>
