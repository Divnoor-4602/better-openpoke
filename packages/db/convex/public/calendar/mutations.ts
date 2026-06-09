import { v } from 'convex/values'

import { internal } from '../../_generated/api'
import { pokeMutation } from '../../auth'
import { vCalendarProvider } from '../../calendar_connection/validators'
import { AUTO_JOIN_CONSENT_VERSION } from '../../compliance/consent'
import { notFound, validationError } from '../../error'

export const setAutoJoin = pokeMutation({
  args: {
    autoJoinConsentVersion: v.optional(v.string()),
    enabled: v.boolean(),
    provider: vCalendarProvider,
  },
  handler: async (ctx, { autoJoinConsentVersion, enabled, provider }) => {
    // Enabling auto-join requires an explicit acknowledgement separate from
    // the per-meeting consent. Disabling does not.
    if (enabled && autoJoinConsentVersion !== AUTO_JOIN_CONSENT_VERSION) {
      validationError({
        entity: 'Consent',
        message: `Auto-join requires acknowledgement (expected ${AUTO_JOIN_CONSENT_VERSION}, got ${String(autoJoinConsentVersion)})`,
      })
    }

    const connection = await ctx.db
      .query('calendarConnections')
      .withIndex('by_user_provider', (q) =>
        q.eq('userId', ctx.user._id).eq('provider', provider),
      )
      .unique()

    if (!connection) {
      notFound({ entity: 'CalendarConnection' })
    }

    await ctx.db.patch(connection._id, {
      autoJoinEnabled: enabled,
      updatedAt: Date.now(),
    })

    await ctx.runMutation(internal.audit_event.mutations.log, {
      action: enabled ? 'autojoin.enabled' : 'autojoin.disabled',
      entityId: connection._id,
      entityType: 'calendar_connection',
      metadata: enabled
        ? { consentVersion: AUTO_JOIN_CONSENT_VERSION }
        : undefined,
      userId: ctx.user._id,
    })

    return { autoJoinEnabled: enabled }
  },
})
