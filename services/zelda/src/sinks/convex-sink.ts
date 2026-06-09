import { api } from '@general-poke/db/api'
import { ConvexHttpClient } from 'convex/browser'

import type { FinalizedTurn, SpeakerRevisionEvent, TurnSink } from '../sink'

export type ConvexSinkOptions = {
  convexUrl: string
}

let sharedClient: ConvexHttpClient | null = null

function getClient(): ConvexHttpClient | null {
  if (sharedClient) return sharedClient
  const url = process.env.CONVEX_URL
  if (!url) return null
  sharedClient = new ConvexHttpClient(url)
  return sharedClient
}

export async function notifyMeetingEnded(opts: {
  listenerToken: string
  meetingId: string
}): Promise<void> {
  const client = getClient()
  if (!client) return
  try {
    await client.mutation(
      api.public.meeting.mutations.markMeetingEndedFromZelda,
      {
        listenerToken: opts.listenerToken,
        meetingId: opts.meetingId as never,
      },
    )
    console.log('[convex-sink] meeting ended', { meetingId: opts.meetingId })
  } catch (err) {
    console.error('[convex-sink] markMeetingEnded failed', err)
  }
}

export async function notifyMeetingRecording(opts: {
  listenerToken: string
  meetingId: string
}): Promise<void> {
  const client = getClient()
  if (!client) return
  try {
    await client.mutation(
      api.public.meeting.mutations.markMeetingRecordingFromZelda,
      {
        listenerToken: opts.listenerToken,
        meetingId: opts.meetingId as never,
      },
    )
    console.log('[convex-sink] meeting recording', { meetingId: opts.meetingId })
  } catch (err) {
    console.error('[convex-sink] markMeetingRecording failed', err)
  }
}

export function createConvexSink(opts: ConvexSinkOptions): TurnSink {
  const client = new ConvexHttpClient(opts.convexUrl)
  sharedClient = client

  return {
    async onSpeakerRevision(event: SpeakerRevisionEvent) {
      try {
        const res = await client.mutation(
          api.public.meeting.mutations.applySpeakerRevisionFromZelda,
          {
            listenerToken: event.listenerToken,
            meetingId: event.meetingId as never,
            revisions: event.revisions.map((r) => ({
              speaker: r.speaker,
              turnOrder: r.turnOrder,
            })),
          },
        )
        console.log('[convex-sink] revision applied', {
          meetingId: event.meetingId,
          patched: res.patched,
        })
      } catch (err) {
        console.error('[convex-sink] applySpeakerRevision failed', err)
      }
    },

    async onTurn(turn: FinalizedTurn) {
      try {
        await client.mutation(
          api.public.meeting.mutations.appendUtteranceFromZelda,
          {
            endMs: turn.endMs,
            listenerToken: turn.listenerToken,
            meetingId: turn.meetingId as never,
            speakerLabel: turn.speaker,
            startMs: turn.startMs,
            text: turn.transcript,
            turnOrder: turn.turnOrder,
          },
        )
      } catch (err) {
        console.error('[convex-sink] appendUtterance failed', err)
      }
    },
  }
}
