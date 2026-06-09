import { v } from 'convex/values'

import { internalMutation } from '../_generated/server'
import { vAuditAction } from './validators'

export const log = internalMutation({
  args: {
    action: vAuditAction,
    entityId: v.optional(v.string()),
    entityType: v.optional(v.string()),
    metadata: v.optional(
      v.object({
        consentVersion: v.optional(v.string()),
        externalEventId: v.optional(v.string()),
        meetingUrl: v.optional(v.string()),
        status: v.optional(v.string()),
      }),
    ),
    userId: v.id('users'),
  },
  handler: async (ctx, args) => {
    return await ctx.db.insert('auditEvents', {
      action: args.action,
      createdAt: Date.now(),
      entityId: args.entityId,
      entityType: args.entityType,
      metadata: args.metadata,
      userId: args.userId,
    })
  },
})
