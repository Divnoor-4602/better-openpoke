import { v } from 'convex/values'

import { pokeQuery } from '../../auth'

export const getById = pokeQuery({
  args: { noteId: v.id('meetingNotes') },
  handler: async (ctx, { noteId }) => {
    const note = await ctx.db.get(noteId)
    if (!note || note.userId !== ctx.user._id) return null
    return note
  },
})

export const getForMeeting = pokeQuery({
  args: { meetingId: v.id('meetings') },
  handler: async (ctx, { meetingId }) => {
    const note = await ctx.db
      .query('meetingNotes')
      .withIndex('by_meeting', (q) => q.eq('meetingId', meetingId))
      .unique()
    if (!note || note.userId !== ctx.user._id) return null
    return note
  },
})

export const listForUser = pokeQuery({
  args: {},
  handler: async (ctx) => {
    return await ctx.db
      .query('meetingNotes')
      .withIndex('by_user_generatedAt', (q) => q.eq('userId', ctx.user._id))
      .order('desc')
      .take(50)
  },
})
