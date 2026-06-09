import { v } from 'convex/values'

import { internalMutation } from '../_generated/server'
import { vOauthProvider } from './validators'

export const createState = internalMutation({
  args: {
    expiresAt: v.number(),
    provider: vOauthProvider,
    state: v.string(),
    userId: v.id('users'),
  },
  handler: async (ctx, args) => {
    return await ctx.db.insert('oauthStates', {
      createdAt: Date.now(),
      expiresAt: args.expiresAt,
      provider: args.provider,
      state: args.state,
      userId: args.userId,
    })
  },
})

export const consumeState = internalMutation({
  args: {
    provider: vOauthProvider,
    state: v.string(),
  },
  handler: async (ctx, { provider: _provider, state }) => {
    const row = await ctx.db
      .query('oauthStates')
      .withIndex('by_state', (q) => q.eq('state', state))
      .unique()

    if (!row) return null
    await ctx.db.delete(row._id)

    if (row.expiresAt < Date.now()) return null

    return row.userId
  },
})
