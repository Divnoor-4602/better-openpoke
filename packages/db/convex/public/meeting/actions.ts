import { v } from 'convex/values'

import { api, internal } from '../../_generated/api'
import { pokeAction } from '../../auth'
import {
  MEETING_CONSENT_TEXT,
  MEETING_CONSENT_VERSION,
} from '../../compliance/consent'
import { validationError } from '../../error'
import { mb } from '../../integrations/meetingbaas'
import { signListenerToken } from '../../integrations/zelda/token'

const SUPPORTED_HOSTS = ['meet.google.com', 'zoom.us', 'teams.microsoft.com']

function ensureConsent(consentVersion: string) {
  if (consentVersion !== MEETING_CONSENT_VERSION) {
    validationError({
      entity: 'Consent',
      message: `Consent version mismatch (expected ${MEETING_CONSENT_VERSION}, got ${consentVersion}). Please re-acknowledge.`,
    })
  }
}

function looksLikeMeetingUrl(url: string): boolean {
  try {
    const u = new URL(url)
    return SUPPORTED_HOSTS.some((h) => u.hostname.endsWith(h))
  } catch {
    return false
  }
}

export const startAdHocMeeting = pokeAction({
  args: {
    consentVersion: v.string(),
    meetingUrl: v.string(),
    title: v.optional(v.string()),
  },
  handler: async (ctx, { consentVersion, meetingUrl, title }) => {
    ensureConsent(consentVersion)
    if (!looksLikeMeetingUrl(meetingUrl)) {
      validationError({
        entity: 'Meeting',
        message: 'Unsupported meeting URL (Google Meet, Zoom, or Teams)',
      })
    }

    const user = await ctx.runQuery(api.public.user.queries.me, {})

    const zeldaBaseUrl = process.env.ZELDA_PUBLIC_URL
    const webhookSecret = process.env.MEETINGBAAS_WEBHOOK_SECRET
    if (!zeldaBaseUrl || !webhookSecret) {
      validationError({
        entity: 'AdHocMeeting',
        message: 'ZELDA_PUBLIC_URL or MEETINGBAAS_WEBHOOK_SECRET not set',
      })
    }

    const meetingId = await ctx.runMutation(
      internal.meeting.mutations.createAdHocMeeting,
      {
        consentText: MEETING_CONSENT_TEXT,
        consentVersion: MEETING_CONSENT_VERSION,
        meetingUrl,
        title,
        userId: user._id,
      },
    )

    await ctx.runMutation(internal.audit_event.mutations.log, {
      action: 'meeting.consent.recorded',
      entityId: meetingId,
      entityType: 'meeting',
      metadata: { consentVersion, meetingUrl },
      userId: user._id,
    })
    await ctx.runMutation(internal.audit_event.mutations.log, {
      action: 'meeting.created',
      entityId: meetingId,
      entityType: 'meeting',
      metadata: { meetingUrl },
      userId: user._id,
    })

    const token = await signListenerToken({ meetingId, userId: user._id })

    const wsBase = zeldaBaseUrl.replace(/^http/, 'ws').replace(/\/$/, '')
    const httpBase = zeldaBaseUrl.replace(/\/$/, '')

    const { botId } = await mb.bots.dispatch({
      callbackUrl: `${httpBase}/webhooks/meetingbaas`,
      listenerWsUrl: `${wsBase}/ws/meeting/${meetingId}?token=${token}`,
      meetingUrl,
      webhookSecret,
    })

    await ctx.runMutation(internal.meeting.mutations.setBotId, {
      botId,
      meetingId,
    })

    return { botId, meetingId }
  },
})

export const deleteMeeting = pokeAction({
  args: { meetingId: v.id('meetings') },
  handler: async (ctx, { meetingId }) => {
    const user = await ctx.runQuery(api.public.user.queries.me, {})

    const meeting = await ctx.runQuery(api.public.meeting.queries.getById, {
      meetingId,
    })
    if (!meeting) {
      validationError({
        entity: 'Meeting',
        id: meetingId,
        message: 'Not found',
      })
    }

    // Best-effort MB cleanup; failure here shouldn't block local deletion.
    if (meeting.botId) {
      try {
        await mb.bots.leave({ botId: meeting.botId })
      } catch (err) {
        console.warn('[delete-meeting] mb leave failed', {
          meetingId,
          // metadata-only, no PII
          reason: String(err).slice(0, 200),
        })
      }
    }

    await ctx.runMutation(internal.meeting.mutations.cascadeDelete, {
      meetingId,
      userId: user._id,
    })

    await ctx.runMutation(internal.audit_event.mutations.log, {
      action: 'meeting.deleted',
      entityId: meetingId,
      entityType: 'meeting',
      userId: user._id,
    })

    return { ok: true as const }
  },
})
