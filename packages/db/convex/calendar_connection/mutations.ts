import { v } from 'convex/values'

import { internalMutation } from '../_generated/server'
import { vCalendarProvider } from './validators'

export const deleteForUser = internalMutation({
  args: {
    provider: vCalendarProvider,
    userId: v.id('users'),
  },
  handler: async (ctx, { provider, userId }) => {
    const existing = await ctx.db
      .query('calendarConnections')
      .withIndex('by_user_provider', (q) =>
        q.eq('userId', userId).eq('provider', provider),
      )
      .unique()

    if (!existing) return null
    const mbCalendarId = existing.mbCalendarId
    await ctx.db.delete(existing._id)
    return { connectionId: existing._id, mbCalendarId }
  },
})

export const upsertFromOauth = internalMutation({
  args: {
    accountEmail: v.string(),
    mbCalendarId: v.string(),
    provider: vCalendarProvider,
    rawCalendarId: v.string(),
    userId: v.id('users'),
  },
  handler: async (ctx, args) => {
    const now = Date.now()
    const existing = await ctx.db
      .query('calendarConnections')
      .withIndex('by_user_provider', (q) =>
        q.eq('userId', args.userId).eq('provider', args.provider),
      )
      .unique()

    if (existing) {
      await ctx.db.patch(existing._id, {
        accountEmail: args.accountEmail,
        mbCalendarId: args.mbCalendarId,
        rawCalendarId: args.rawCalendarId,
        status: 'active',
        updatedAt: now,
      })
      return existing._id
    }

    return await ctx.db.insert('calendarConnections', {
      accountEmail: args.accountEmail,
      autoJoinEnabled: false,
      connectedAt: now,
      mbCalendarId: args.mbCalendarId,
      provider: args.provider,
      rawCalendarId: args.rawCalendarId,
      status: 'active',
      updatedAt: now,
      userId: args.userId,
    })
  },
})
