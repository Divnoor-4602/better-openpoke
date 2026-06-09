import type { UserJSON } from '@clerk/backend'
import type { Validator } from 'convex/values'

import { v } from 'convex/values'

import { internalMutation } from '../../_generated/server'
import { getUserByClerkId, primaryEmail } from '../../user/helpers'

export const upsertFromClerk = internalMutation({
  args: { data: v.any() as Validator<UserJSON> },
  handler: async (ctx, { data }) => {
    const attrs = { clerkId: data.id, email: primaryEmail(data) }
    const existing = await getUserByClerkId(ctx, data.id)
    if (existing) {
      await ctx.db.patch(existing._id, attrs)
    } else {
      await ctx.db.insert('users', attrs)
    }
  },
})

export const deleteFromClerk = internalMutation({
  args: { clerkUserId: v.string() },
  handler: async (ctx, { clerkUserId }) => {
    const user = await getUserByClerkId(ctx, clerkUserId)
    if (user) {
      await ctx.db.delete(user._id)
    } else {
      console.warn(`No user row for Clerk user ID: ${clerkUserId}`)
    }
  },
})
