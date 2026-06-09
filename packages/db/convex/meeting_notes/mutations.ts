import { v } from 'convex/values'

import { internalMutation } from '../_generated/server'

export const upsertForMeeting = internalMutation({
  args: {
    content: v.string(),
    meetingId: v.id('meetings'),
    title: v.string(),
    userId: v.id('users'),
  },
  handler: async (ctx, args) => {
    const existing = await ctx.db
      .query('meetingNotes')
      .withIndex('by_meeting', (q) => q.eq('meetingId', args.meetingId))
      .unique()

    const now = Date.now()

    if (existing) {
      await ctx.db.patch(existing._id, {
        content: args.content,
        generatedAt: now,
        title: args.title,
        updatedAt: now,
      })
      return existing._id
    }

    return await ctx.db.insert('meetingNotes', {
      content: args.content,
      generatedAt: now,
      meetingId: args.meetingId,
      title: args.title,
      updatedAt: now,
      userId: args.userId,
    })
  },
})
