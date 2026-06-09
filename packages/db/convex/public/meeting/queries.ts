import { v } from 'convex/values'

import { pokeQuery } from '../../auth'

export const listMyMeetings = pokeQuery({
  args: {},
  handler: async (ctx) => {
    const meetings = await ctx.db
      .query('meetings')
      .withIndex('by_user', (q) => q.eq('userId', ctx.user._id))
      .order('desc')
      .take(20)

    return await Promise.all(
      meetings.map(async (m) => {
        const note = await ctx.db
          .query('meetingNotes')
          .withIndex('by_meeting', (q) => q.eq('meetingId', m._id))
          .unique()
        return { ...m, noteId: note?._id ?? null }
      }),
    )
  },
})

export const getById = pokeQuery({
  args: { meetingId: v.id('meetings') },
  handler: async (ctx, { meetingId }) => {
    const meeting = await ctx.db.get(meetingId)
    if (!meeting || meeting.userId !== ctx.user._id) return null
    const note = await ctx.db
      .query('meetingNotes')
      .withIndex('by_meeting', (q) => q.eq('meetingId', meetingId))
      .unique()
    return { ...meeting, noteId: note?._id ?? null }
  },
})

export const listTranscriptTurns = pokeQuery({
  args: { meetingId: v.id('meetings') },
  handler: async (ctx, { meetingId }) => {
    const meeting = await ctx.db.get(meetingId)
    if (!meeting || meeting.userId !== ctx.user._id) return []
    return await ctx.db
      .query('meetingTranscriptTurns')
      .withIndex('by_meeting_turnOrder', (q) => q.eq('meetingId', meetingId))
      .order('asc')
      .collect()
  },
})
