import { v } from 'convex/values'

import { internal } from '../../_generated/api'
import { mutation } from '../../_generated/server'
import { notFound, validationError } from '../../error'
import { verifyListenerToken } from '../../integrations/zelda/token'

export const appendUtteranceFromZelda = mutation({
  args: {
    endMs: v.union(v.number(), v.null()),
    listenerToken: v.string(),
    meetingId: v.id('meetings'),
    speakerLabel: v.union(v.string(), v.null()),
    startMs: v.union(v.number(), v.null()),
    text: v.string(),
    turnOrder: v.number(),
  },
  handler: async (ctx, args) => {
    const claims = await verifyListenerToken(args.listenerToken)
    if (claims.meetingId !== args.meetingId) {
      validationError({
        entity: 'MeetingTranscriptTurn',
        message: 'Token meeting mismatch',
      })
    }

    const meeting = await ctx.db.get(args.meetingId)
    if (!meeting) notFound({ entity: 'Meeting', id: args.meetingId })
    if (meeting.userId !== claims.userId) {
      validationError({
        entity: 'MeetingTranscriptTurn',
        message: 'Token user mismatch',
      })
    }

    return await ctx.db.insert('meetingTranscriptTurns', {
      createdAt: Date.now(),
      endMs: args.endMs ?? undefined,
      meetingId: args.meetingId,
      speakerLabel: args.speakerLabel ?? undefined,
      startMs: args.startMs ?? undefined,
      text: args.text,
      turnOrder: args.turnOrder,
      userId: claims.userId,
    })
  },
})

export const applySpeakerRevisionFromZelda = mutation({
  args: {
    listenerToken: v.string(),
    meetingId: v.id('meetings'),
    revisions: v.array(
      v.object({
        speaker: v.union(v.string(), v.null()),
        turnOrder: v.number(),
      }),
    ),
  },
  handler: async (ctx, args) => {
    const claims = await verifyListenerToken(args.listenerToken)
    if (claims.meetingId !== args.meetingId) {
      validationError({
        entity: 'MeetingTranscriptTurn',
        message: 'Token meeting mismatch',
      })
    }

    let patched = 0
    for (const rev of args.revisions) {
      const row = await ctx.db
        .query('meetingTranscriptTurns')
        .withIndex('by_meeting_turnOrder', (q) =>
          q.eq('meetingId', args.meetingId).eq('turnOrder', rev.turnOrder),
        )
        .unique()
      if (!row) continue
      await ctx.db.patch(row._id, {
        speakerLabel: rev.speaker ?? undefined,
      })
      patched += 1
    }

    return { patched }
  },
})

export const markMeetingRecordingFromZelda = mutation({
  args: {
    listenerToken: v.string(),
    meetingId: v.id('meetings'),
  },
  handler: async (ctx, { listenerToken, meetingId }) => {
    const claims = await verifyListenerToken(listenerToken)
    if (claims.meetingId !== meetingId) {
      validationError({
        entity: 'Meeting',
        message: 'Token meeting mismatch',
      })
    }
    const meeting = await ctx.db.get(meetingId)
    if (!meeting) notFound({ entity: 'Meeting', id: meetingId })
    if (meeting.userId !== claims.userId) {
      validationError({ entity: 'Meeting', message: 'Token user mismatch' })
    }
    if (meeting.status === 'ended' || meeting.status === 'failed') {
      return { ok: false as const }
    }
    if (meeting.status !== 'recording') {
      await ctx.db.patch(meetingId, {
        startedAt: meeting.startedAt ?? Date.now(),
        status: 'recording',
        updatedAt: Date.now(),
      })
    }
    return { ok: true as const }
  },
})

export const markMeetingEndedFromZelda = mutation({
  args: {
    listenerToken: v.string(),
    meetingId: v.id('meetings'),
  },
  handler: async (ctx, { listenerToken, meetingId }) => {
    const claims = await verifyListenerToken(listenerToken)
    if (claims.meetingId !== meetingId) {
      validationError({
        entity: 'Meeting',
        message: 'Token meeting mismatch',
      })
    }

    const meeting = await ctx.db.get(meetingId)
    if (!meeting) notFound({ entity: 'Meeting', id: meetingId })
    if (meeting.userId !== claims.userId) {
      validationError({ entity: 'Meeting', message: 'Token user mismatch' })
    }
    if (meeting.status === 'ended' || meeting.status === 'failed') {
      return { alreadyEnded: true as const }
    }

    const now = Date.now()
    await ctx.db.patch(meetingId, {
      endedAt: now,
      notesStatus: 'pending',
      status: 'ended',
      updatedAt: now,
    })

    // Schedule note generation. Defer briefly so any in-flight utterance
    // mutations from zelda land before the agent reads the transcript.
    await ctx.scheduler.runAfter(
      2000,
      internal.meeting_notes.actions.generate,
      { meetingId, userId: claims.userId },
    )

    return { alreadyEnded: false as const }
  },
})
