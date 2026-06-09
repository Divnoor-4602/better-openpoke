import { v } from 'convex/values'

import { internal } from '../_generated/api'
import { internalAction } from '../_generated/server'
import { validationError } from '../error'
import { mb } from '../integrations/meetingbaas'
import { signListenerToken } from '../integrations/zelda/token'

const CONSENT_TEXT =
  'I confirm I have obtained all required consent from participants before recording or transcribing this conversation.'
const CONSENT_VERSION = 'v1'

export const dispatchBotForEvent = internalAction({
  args: {
    eventId: v.string(),
    mbCalendarId: v.string(),
    meetingUrl: v.string(),
    seriesId: v.string(),
    title: v.optional(v.string()),
    userId: v.id('users'),
  },
  handler: async (ctx, args) => {
    const zeldaBaseUrl = process.env.ZELDA_PUBLIC_URL
    const webhookSecret = process.env.MEETINGBAAS_WEBHOOK_SECRET
    if (!zeldaBaseUrl || !webhookSecret) {
      validationError({
        entity: 'ScheduleBot',
        message: 'ZELDA_PUBLIC_URL or MEETINGBAAS_WEBHOOK_SECRET not set',
      })
    }

    // Dedup: if a non-terminal meeting already exists for this calendar event,
    // reuse it. MB's createCalendarBot is idempotent per event_id, so calling
    // it again just refreshes the same MB-side schedule.
    const existing = await ctx.runQuery(
      internal.meeting.queries.findByCalendarEvent,
      { externalEventId: args.eventId, userId: args.userId },
    )
    const reusable =
      existing && existing.status !== 'ended' && existing.status !== 'failed'
        ? existing
        : null

    const meetingId = reusable
      ? reusable._id
      : await ctx.runMutation(
          internal.meeting.mutations.createForCalendarEvent,
          {
            consentText: CONSENT_TEXT,
            consentVersion: CONSENT_VERSION,
            externalEventId: args.eventId,
            mbCalendarId: args.mbCalendarId,
            meetingUrl: args.meetingUrl,
            title: args.title,
            userId: args.userId,
          },
        )

    const token = await signListenerToken({ meetingId, userId: args.userId })

    const wsBase = zeldaBaseUrl.replace(/^http/, 'ws').replace(/\/$/, '')
    const httpBase = zeldaBaseUrl.replace(/\/$/, '')

    const dispatchResult = await mb.calendar.scheduleBot({
      allOccurrences: false,
      callbackUrl: `${httpBase}/webhooks/meetingbaas`,
      eventId: args.eventId,
      listenerWsUrl: `${wsBase}/ws/meeting/${meetingId}?token=${token}`,
      mbCalendarId: args.mbCalendarId,
      seriesId: args.seriesId,
      webhookSecret,
    })

    const botId = dispatchResult.scheduledEventIds[0] ?? args.eventId
    await ctx.runMutation(internal.meeting.mutations.setBotId, {
      botId,
      meetingId,
    })

    return { meetingId, scheduledEventIds: dispatchResult.scheduledEventIds }
  },
})
