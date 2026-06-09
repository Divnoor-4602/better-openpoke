import { defineSchema } from 'convex/server'

import { Meeting } from './meeting/validators'
import { MeetingTranscriptTurn } from './meeting_transcription_turn/validators'
import { User } from './user/validators'

export default defineSchema({
  meetings: Meeting.table
    .index('by_user', ['userId'])
    .index('by_user_status', ['userId', 'status'])
    .index('by_botId', ['botId'])
    .index('by_transcriptionSessionId', ['transcriptionSessionId']),
  meetingTranscriptTurns: MeetingTranscriptTurn.table
    .index('by_meeting_turnOrder', ['meetingId', 'turnOrder'])
    .index('by_meeting_createdAt', ['meetingId', 'createdAt']),
  users: User.table.index('by_clerkId', ['clerkId']),
})
