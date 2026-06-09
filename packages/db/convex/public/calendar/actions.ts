import { v } from 'convex/values'

import { api, internal } from '../../_generated/api'
import { pokeAction } from '../../auth'
import { vCalendarProvider } from '../../calendar_connection/validators'
import { MEETING_CONSENT_VERSION } from '../../compliance/consent'
import { validationError } from '../../error'
import { google } from '../../integrations/google'
import { mb } from '../../integrations/meetingbaas'

const STATE_TTL_MS = 10 * 60 * 1000

function ensureMeetingConsent(consentVersion: string) {
  if (consentVersion !== MEETING_CONSENT_VERSION) {
    validationError({
      entity: 'Consent',
      message: `Consent version mismatch (expected ${MEETING_CONSENT_VERSION}, got ${consentVersion})`,
    })
  }
}

export const startGoogleOauth = pokeAction({
  args: {},
  handler: async (ctx) => {
    const user = await ctx.runQuery(api.public.user.queries.me, {})
    const state = crypto.randomUUID()

    await ctx.runMutation(internal.oauth_state.mutations.createState, {
      expiresAt: Date.now() + STATE_TTL_MS,
      provider: 'google',
      state,
      userId: user._id,
    })

    return google.oauth.buildAuthUrl({ state })
  },
})

export const disconnectCalendar = pokeAction({
  args: { provider: vCalendarProvider },
  handler: async (ctx, { provider }) => {
    const user = await ctx.runQuery(api.public.user.queries.me, {})

    const connection = await ctx.runQuery(
      api.public.calendar.queries.getCalendarConnection,
      { provider },
    )
    if (!connection) {
      validationError({
        entity: 'CalendarConnection',
        message: 'No calendar connected',
      })
    }

    await mb.calendar.deleteConnection({
      mbCalendarId: connection.mbCalendarId,
    })

    await ctx.runMutation(
      internal.calendar_connection.mutations.deleteForUser,
      {
        provider,
        userId: user._id,
      },
    )

    return { ok: true as const }
  },
})

export const listUpcomingEvents = pokeAction({
  args: {
    provider: vCalendarProvider,
    startAfter: v.optional(v.string()),
  },
  handler: async (ctx, { provider, startAfter }) => {
    const connection = await ctx.runQuery(
      api.public.calendar.queries.getCalendarConnection,
      { provider },
    )
    if (!connection) {
      validationError({
        entity: 'CalendarConnection',
        message: 'No calendar connected',
      })
    }

    return await mb.calendar.listEvents({
      mbCalendarId: connection.mbCalendarId,
      startAfter:
        startAfter ?? new Date().toISOString().replace(/\.\d+Z$/, 'Z'),
    })
  },
})

export const scheduleBotForEvent = pokeAction({
  args: {
    consentVersion: v.string(),
    eventId: v.string(),
    mbCalendarId: v.string(),
    meetingUrl: v.string(),
    provider: vCalendarProvider,
    seriesId: v.string(),
    title: v.optional(v.string()),
  },
  handler: async (ctx, args) => {
    ensureMeetingConsent(args.consentVersion)
    const user = await ctx.runQuery(api.public.user.queries.me, {})

    const connection = await ctx.runQuery(
      api.public.calendar.queries.getCalendarConnection,
      { provider: args.provider },
    )
    if (!connection || connection.mbCalendarId !== args.mbCalendarId) {
      validationError({
        entity: 'CalendarConnection',
        message: 'Calendar mismatch',
      })
    }

    const result = await ctx.runAction(
      internal.meeting.actions.dispatchBotForEvent,
      {
        eventId: args.eventId,
        mbCalendarId: args.mbCalendarId,
        meetingUrl: args.meetingUrl,
        seriesId: args.seriesId,
        title: args.title,
        userId: user._id,
      },
    )

    await ctx.runMutation(internal.audit_event.mutations.log, {
      action: 'meeting.consent.recorded',
      entityId: result.meetingId,
      entityType: 'meeting',
      metadata: {
        consentVersion: args.consentVersion,
        externalEventId: args.eventId,
      },
      userId: user._id,
    })

    return result
  },
})

export const cancelBotForEvent = pokeAction({
  args: {
    eventId: v.string(),
    mbCalendarId: v.string(),
    provider: vCalendarProvider,
  },
  handler: async (ctx, { eventId, mbCalendarId, provider }) => {
    const user = await ctx.runQuery(api.public.user.queries.me, {})

    const connection = await ctx.runQuery(
      api.public.calendar.queries.getCalendarConnection,
      { provider },
    )
    if (!connection || connection.mbCalendarId !== mbCalendarId) {
      validationError({
        entity: 'CalendarConnection',
        message: 'Calendar mismatch',
      })
    }

    await mb.calendar.deleteCalendarBot({ eventId, mbCalendarId })

    const meeting = await ctx.runQuery(
      internal.meeting.queries.findByCalendarEvent,
      { externalEventId: eventId, userId: user._id },
    )
    if (meeting) {
      await ctx.runMutation(internal.meeting.mutations.markCancelled, {
        meetingId: meeting._id,
      })
    }

    return { ok: true as const }
  },
})
