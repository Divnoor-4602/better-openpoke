import type { MeetingBaasClient } from '../client'
import type {
  CreateConnectionInput,
  CreateConnectionOutput,
  DeleteCalendarBotInput,
  DeleteCalendarBotOutput,
  DeleteConnectionInput,
  DeleteConnectionOutput,
  ListEventsInput,
  ListEventsOutput,
  ScheduleBotInput,
  ScheduleBotOutput,
} from './schema'

import { validationError } from '../../../error'
import {
  CreateConnectionInputSchema,
  CreateConnectionOutputSchema,
  DeleteCalendarBotInputSchema,
  DeleteCalendarBotOutputSchema,
  DeleteConnectionInputSchema,
  DeleteConnectionOutputSchema,
  ListEventsInputSchema,
  ListEventsOutputSchema,
  ScheduleBotInputSchema,
  ScheduleBotOutputSchema,
} from './schema'

const DEFAULT_BOT_NAME = 'Legal Poke Notes'
const STREAMING_AUDIO_FREQUENCY = 24000

export async function createConnection(
  client: MeetingBaasClient,
  input: CreateConnectionInput,
): Promise<CreateConnectionOutput> {
  const args = CreateConnectionInputSchema.parse(input)

  const oauthClientId = process.env.GOOGLE_OAUTH_CLIENT_ID
  const oauthClientSecret = process.env.GOOGLE_OAUTH_CLIENT_SECRET
  if (!oauthClientId || !oauthClientSecret) {
    validationError({
      entity: 'MeetingBaasCalendar',
      message: 'GOOGLE_OAUTH_CLIENT_ID/SECRET not set',
    })
  }

  const res = await client.sdk.createCalendarConnection({
    calendar_platform: 'google',
    oauth_client_id: oauthClientId,
    oauth_client_secret: oauthClientSecret,
    oauth_refresh_token: args.refreshToken,
    raw_calendar_id: args.rawCalendarId,
  })

  if (!res.success) {
    validationError({
      entity: 'MeetingBaasCalendar',
      message: `createConnection failed: ${res.message}`,
    })
  }

  const parsed = CreateConnectionOutputSchema.safeParse({
    accountEmail: res.data.account_email,
    mbCalendarId: res.data.calendar_id,
  })
  if (!parsed.success) {
    validationError({
      entity: 'MeetingBaasCalendar',
      message: `createConnection response invalid: ${parsed.error.message}`,
    })
  }
  return parsed.data
}

export async function deleteCalendarBot(
  client: MeetingBaasClient,
  input: DeleteCalendarBotInput,
): Promise<DeleteCalendarBotOutput> {
  const args = DeleteCalendarBotInputSchema.parse(input)

  const res = await client.sdk.deleteCalendarBot({
    calendar_id: args.mbCalendarId,
    event_id: args.eventId,
  })

  if (!res.success) {
    validationError({
      entity: 'MeetingBaasCalendar',
      id: args.mbCalendarId,
      message: `deleteCalendarBot failed: ${res.message}`,
    })
  }

  const parsed = DeleteCalendarBotOutputSchema.safeParse({
    eventId: args.eventId,
    ok: true,
  })
  if (!parsed.success) {
    validationError({
      entity: 'MeetingBaasCalendar',
      id: args.mbCalendarId,
      message: `deleteCalendarBot response invalid: ${parsed.error.message}`,
    })
  }
  return parsed.data
}

export async function deleteConnection(
  client: MeetingBaasClient,
  input: DeleteConnectionInput,
): Promise<DeleteConnectionOutput> {
  const args = DeleteConnectionInputSchema.parse(input)

  const res = await client.sdk.deleteCalendarConnection({
    calendar_id: args.mbCalendarId,
  })

  if (!res.success) {
    validationError({
      entity: 'MeetingBaasCalendar',
      id: args.mbCalendarId,
      message: `deleteConnection failed: ${res.message}`,
    })
  }

  const parsed = DeleteConnectionOutputSchema.safeParse({
    mbCalendarId: args.mbCalendarId,
    ok: true,
  })
  if (!parsed.success) {
    validationError({
      entity: 'MeetingBaasCalendar',
      id: args.mbCalendarId,
      message: `deleteConnection response invalid: ${parsed.error.message}`,
    })
  }
  return parsed.data
}

export async function listEvents(
  _client: MeetingBaasClient,
  input: ListEventsInput,
): Promise<ListEventsOutput> {
  const args = ListEventsInputSchema.parse(input)

  const apiKey = process.env.MEETINGBAAS_API_KEY
  if (!apiKey) {
    validationError({
      entity: 'MeetingBaasCalendar',
      message: 'MEETINGBAAS_API_KEY is not set',
    })
  }

  // The MB SDK's listEvents has a bug where it serializes query params into the
  // GET request body, which the Fetch API rejects. Bypass with raw fetch.
  const params = new URLSearchParams({
    limit: '50',
    show_cancelled: 'false',
  })
  if (args.startAfter) params.set('start_date', args.startAfter)

  const url = `https://api.meetingbaas.com/v2/calendars/${args.mbCalendarId}/events?${params.toString()}`
  const res = await fetch(url, {
    headers: { 'x-meeting-baas-api-key': apiKey },
    method: 'GET',
  })

  const body = (await res.json().catch(() => null)) as null | {
    data?: unknown[]
    message?: string
  }

  if (!res.ok) {
    console.error('[mb-listEvents] failure', { body, status: res.status })
    validationError({
      entity: 'MeetingBaasCalendar',
      id: args.mbCalendarId,
      message: `listEvents failed: ${res.status} ${body?.message ?? ''}`,
    })
  }

  const rawData = (body?.data ?? []) as {
    bot_scheduled: boolean
    end_time: string
    event_id: string
    is_exception: boolean
    meeting_platform: 'meet' | 'teams' | 'zoom' | null
    meeting_url: null | string
    series_id: string
    start_time: string
    status: 'cancelled' | 'confirmed' | 'tentative'
    title: string
  }[]

  const events = rawData.map((e) => ({
    botScheduled: e.bot_scheduled,
    endTime: e.end_time,
    eventId: e.event_id,
    isException: e.is_exception,
    meetingPlatform: e.meeting_platform,
    meetingUrl: e.meeting_url,
    seriesId: e.series_id,
    startTime: e.start_time,
    status: e.status,
    title: e.title,
  }))

  const parsed = ListEventsOutputSchema.safeParse({ events })
  if (!parsed.success) {
    validationError({
      entity: 'MeetingBaasCalendar',
      id: args.mbCalendarId,
      message: `listEvents response invalid: ${parsed.error.message}`,
    })
  }
  return parsed.data
}

export async function scheduleBot(
  client: MeetingBaasClient,
  input: ScheduleBotInput,
): Promise<ScheduleBotOutput> {
  const args = ScheduleBotInputSchema.parse(input)

  const res = await client.sdk.createCalendarBot({
    body: {
      all_occurrences: args.allOccurrences,
      bot_name: args.botName ?? DEFAULT_BOT_NAME,
      callback_config: {
        method: 'POST',
        secret: args.webhookSecret,
        url: args.callbackUrl,
      },
      callback_enabled: true,
      event_id: args.eventId,
      recording_mode: 'audio_only',
      series_id: args.seriesId,
      streaming_config: {
        audio_frequency: STREAMING_AUDIO_FREQUENCY,
        input_url: args.listenerWsUrl,
      },
      streaming_enabled: true,
    },
    calendar_id: args.mbCalendarId,
  })

  if (!res.success) {
    validationError({
      entity: 'MeetingBaasCalendar',
      id: args.mbCalendarId,
      message: `scheduleBot failed: ${res.message}`,
    })
  }

  const parsed = ScheduleBotOutputSchema.safeParse({
    scheduledEventIds: res.data.map((item) => item.event_id),
  })
  if (!parsed.success) {
    validationError({
      entity: 'MeetingBaasCalendar',
      id: args.mbCalendarId,
      message: `scheduleBot response invalid: ${parsed.error.message}`,
    })
  }
  return parsed.data
}
