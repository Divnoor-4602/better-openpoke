import { v } from 'convex/values'

import { internalQuery } from '../_generated/server'

export const findByMbCalendarId = internalQuery({
  args: { mbCalendarId: v.string() },
  handler: async (ctx, { mbCalendarId }) => {
    return await ctx.db
      .query('calendarConnections')
      .withIndex('by_mbCalendarId', (q) => q.eq('mbCalendarId', mbCalendarId))
      .unique()
  },
})
