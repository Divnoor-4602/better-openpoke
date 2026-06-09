import type { WebhookEvent } from '@clerk/backend'

import { httpRouter } from 'convex/server'
import { Webhook } from 'svix'

import { internal } from './_generated/api'
import { httpAction } from './_generated/server'
import { google } from './integrations/google'
import { mb } from './integrations/meetingbaas'

const http = httpRouter()

http.route({
  handler: httpAction(async (ctx, request) => {
    const event = await validateRequest(request)
    if (!event) {
      return new Response('Error occurred', { status: 400 })
    }

    switch (event.type) {
      case 'user.created':
      case 'user.updated':
        await ctx.runMutation(
          internal.integrations.clerk.user.upsertFromClerk,
          {
            data: event.data,
          },
        )
        break

      case 'user.deleted': {
        const clerkUserId = event.data.id
        if (clerkUserId) {
          await ctx.runMutation(
            internal.integrations.clerk.user.deleteFromClerk,
            {
              clerkUserId,
            },
          )
        }
        break
      }

      default:
        console.log('Ignored Clerk webhook event', event.type)
    }

    return new Response(null, { status: 200 })
  }),
  method: 'POST',
  path: '/clerk-users-webhook',
})

http.route({
  handler: httpAction(async (ctx, request) => {
    const url = new URL(request.url)
    const code = url.searchParams.get('code')
    const state = url.searchParams.get('state')
    const errorParam = url.searchParams.get('error')

    const appUrl = process.env.LEGAL_POKE_APP_URL
    if (!appUrl) {
      console.error('LEGAL_POKE_APP_URL is not set')
      return new Response('Server misconfigured', { status: 500 })
    }

    const redirectBack = (
      status: 'connected' | 'error',
      reason?: string,
    ): Response => {
      const target = new URL(`${appUrl.replace(/\/$/, '')}/`)
      target.searchParams.set('calendar', status)
      if (reason) target.searchParams.set('reason', reason)
      return new Response(null, {
        headers: { Location: target.toString() },
        status: 302,
      })
    }

    if (errorParam) return redirectBack('error', errorParam)
    if (!code || !state) return redirectBack('error', 'missing_params')

    try {
      const userId = await ctx.runMutation(
        internal.oauth_state.mutations.consumeState,
        { provider: 'google', state },
      )
      if (!userId) return redirectBack('error', 'invalid_state')

      const tokens = await google.oauth.exchangeCode({ code })

      const mbResult = await mb.calendar.createConnection({
        rawCalendarId: 'primary',
        refreshToken: tokens.refreshToken,
      })

      await ctx.runMutation(
        internal.calendar_connection.mutations.upsertFromOauth,
        {
          accountEmail: mbResult.accountEmail,
          mbCalendarId: mbResult.mbCalendarId,
          provider: 'google',
          rawCalendarId: 'primary',
          userId,
        },
      )

      return redirectBack('connected')
    } catch (err) {
      console.error('Google OAuth callback failed', err)
      return redirectBack('error', 'server_error')
    }
  }),
  method: 'GET',
  path: '/oauth/google/callback',
})

type MbCalendarWebhookBody = {
  data?: {
    calendar_id?: string
    event?: {
      end_time?: string
      event_id?: string
      meeting_url?: null | string
      series_id?: string
      start_time?: string
      title?: string
    }
  }
  event?: string
  type?: string
}

http.route({
  handler: httpAction(async (ctx, request) => {
    const secret = process.env.MEETINGBAAS_CALENDAR_WEBHOOK_SECRET
    if (!secret) {
      console.error('MEETINGBAAS_CALENDAR_WEBHOOK_SECRET not set')
      return new Response('Server misconfigured', { status: 500 })
    }

    const payload = await request.text()
    const svixHeaders = {
      'svix-id': request.headers.get('svix-id') ?? '',
      'svix-signature': request.headers.get('svix-signature') ?? '',
      'svix-timestamp': request.headers.get('svix-timestamp') ?? '',
    }
    let body: MbCalendarWebhookBody
    try {
      body = new Webhook(secret).verify(
        payload,
        svixHeaders,
      ) as MbCalendarWebhookBody
    } catch (err) {
      console.error('mb calendar webhook signature invalid', err)
      return new Response('Unauthorized', { status: 401 })
    }

    const eventType = (body.event ?? body.type ?? '').toLowerCase()
    const calendarId = body.data?.calendar_id
    const eventInfo = body.data?.event
    const eventId = eventInfo?.event_id

    console.log('[mb-calendar-webhook]', { calendarId, eventId, eventType })

    if (!calendarId || !eventId) {
      return new Response('OK')
    }

    const connection = await ctx.runQuery(
      internal.calendar_connection.queries.findByMbCalendarId,
      { mbCalendarId: calendarId },
    )
    if (!connection) {
      return new Response('OK')
    }

    if (eventType.includes('delet') || eventType.includes('cancel')) {
      const meeting = await ctx.runQuery(
        internal.meeting.queries.findByCalendarEvent,
        { externalEventId: eventId, userId: connection.userId },
      )
      if (meeting?.botId) {
        try {
          await mb.calendar.deleteCalendarBot({
            eventId,
            mbCalendarId: calendarId,
          })
        } catch (err) {
          console.error('deleteCalendarBot failed during webhook', err)
        }
        await ctx.runMutation(internal.meeting.mutations.markCancelled, {
          meetingId: meeting._id,
          reason: 'event_deleted',
        })
      }
      return new Response('OK')
    }

    if (!connection.autoJoinEnabled) {
      return new Response('OK')
    }
    if (!eventInfo.meeting_url || !eventInfo.series_id) {
      return new Response('OK')
    }

    const existing = await ctx.runQuery(
      internal.meeting.queries.findByCalendarEvent,
      { externalEventId: eventId, userId: connection.userId },
    )
    if (existing) {
      return new Response('OK')
    }

    try {
      await ctx.runAction(internal.meeting.actions.dispatchBotForEvent, {
        eventId,
        mbCalendarId: calendarId,
        meetingUrl: eventInfo.meeting_url,
        seriesId: eventInfo.series_id,
        title: eventInfo.title,
        userId: connection.userId,
      })
    } catch (err) {
      console.error('dispatchBotForEvent failed during webhook', err)
    }

    return new Response('OK')
  }),
  method: 'POST',
  path: '/webhooks/meetingbaas/calendar',
})

async function validateRequest(req: Request): Promise<null | WebhookEvent> {
  const payloadString = await req.text()
  const svixHeaders = {
    'svix-id': req.headers.get('svix-id') ?? '',
    'svix-signature': req.headers.get('svix-signature') ?? '',
    'svix-timestamp': req.headers.get('svix-timestamp') ?? '',
  }
  const secret = process.env.CLERK_WEBHOOK_SECRET
  if (!secret) {
    console.error('Missing CLERK_WEBHOOK_SECRET')
    return null
  }
  const wh = new Webhook(secret)
  try {
    return wh.verify(payloadString, svixHeaders) as WebhookEvent
  } catch (error) {
    console.error('Error verifying webhook event', error)
    return null
  }
}

export default http
