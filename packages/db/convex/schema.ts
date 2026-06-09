import { defineSchema } from 'convex/server'

import { AuditEvent } from './audit_event/validators'
import { CalendarConnection } from './calendar_connection/validators'
import { CalendarEvent } from './calendar_event/validators'
import { Meeting } from './meeting/validators'
import { MeetingNotes } from './meeting_notes/validators'
import { MeetingTranscriptTurn } from './meeting_transcription_turn/validators'
import { OauthState } from './oauth_state/validators'
import { User } from './user/validators'

export default defineSchema({
  auditEvents: AuditEvent.table
    .index('by_user_createdAt', ['userId', 'createdAt'])
    .index('by_user_action', ['userId', 'action']),
  calendarConnections: CalendarConnection.table
    .index('by_user', ['userId'])
    .index('by_user_provider', ['userId', 'provider'])
    .index('by_mbCalendarId', ['mbCalendarId']),
  calendarEvents: CalendarEvent.table
    .index('by_user_startTime', ['userId', 'startTime'])
    .index('by_calendar_event', ['calendarConnectionId', 'eventId'])
    .index('by_calendar_startTime', ['calendarConnectionId', 'startTime'])
    .index('by_mb_event', ['mbCalendarId', 'eventId']),
  meetingNotes: MeetingNotes.table
    .index('by_meeting', ['meetingId'])
    .index('by_user_generatedAt', ['userId', 'generatedAt']),
  meetings: Meeting.table
    .index('by_user', ['userId'])
    .index('by_user_status', ['userId', 'status'])
    .index('by_botId', ['botId'])
    .index('by_user_externalEventId', ['userId', 'externalEventId'])
    .index('by_transcriptionSessionId', ['transcriptionSessionId']),
  meetingTranscriptTurns: MeetingTranscriptTurn.table
    .index('by_meeting_turnOrder', ['meetingId', 'turnOrder'])
    .index('by_meeting_createdAt', ['meetingId', 'createdAt']),
  oauthStates: OauthState.table
    .index('by_state', ['state'])
    .index('by_user_provider', ['userId', 'provider'])
    .index('by_expiresAt', ['expiresAt']),
  users: User.table.index('by_clerkId', ['clerkId']),
})
