import { v } from 'convex/values'

import { internalQuery } from '../_generated/server'

export const getTranscriptText = internalQuery({
  args: {
    meetingId: v.id('meetings'),
    userId: v.id('users'),
  },
  handler: async (ctx, { meetingId, userId }) => {
    const meeting = await ctx.db.get(meetingId)
    if (!meeting || meeting.userId !== userId) return null

    const turns = await ctx.db
      .query('meetingTranscriptTurns')
      .withIndex('by_meeting_turnOrder', (q) => q.eq('meetingId', meetingId))
      .order('asc')
      .collect()

    if (turns.length === 0) return null

    return {
      title: meeting.title ?? null,
      transcript: turns
        .map((t) => `${t.speakerLabel ?? '?'}: ${t.text}`)
        .join('\n'),
      turnCount: turns.length,
    }
  },
})

export const findByCalendarEvent = internalQuery({
  args: {
    externalEventId: v.string(),
    userId: v.id('users'),
  },
  handler: async (ctx, { externalEventId, userId }) => {
    return await ctx.db
      .query('meetings')
      .withIndex('by_user_externalEventId', (q) =>
        q.eq('userId', userId).eq('externalEventId', externalEventId),
      )
      .order('desc')
      .first()
  },
})
