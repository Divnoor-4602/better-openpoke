import { v } from 'convex/values'

import { internalMutation } from '../_generated/server'
import { notFound } from '../error'

export const createForCalendarEvent = internalMutation({
  args: {
    consentText: v.string(),
    consentVersion: v.string(),
    externalEventId: v.string(),
    mbCalendarId: v.string(),
    meetingUrl: v.string(),
    title: v.optional(v.string()),
    userId: v.id('users'),
  },
  handler: async (ctx, args) => {
    const now = Date.now()
    return await ctx.db.insert('meetings', {
      consentConfirmedAt: now,
      consentText: args.consentText,
      consentVersion: args.consentVersion,
      createdAt: now,
      externalEventId: args.externalEventId,
      listenerProvider: 'meetingbaas',
      mbCalendarId: args.mbCalendarId,
      meetingUrl: args.meetingUrl,
      status: 'created',
      title: args.title,
      transcriptionProvider: 'assemblyai',
      updatedAt: now,
      userId: args.userId,
    })
  },
})

export const createAdHocMeeting = internalMutation({
  args: {
    consentText: v.string(),
    consentVersion: v.string(),
    meetingUrl: v.string(),
    title: v.optional(v.string()),
    userId: v.id('users'),
  },
  handler: async (ctx, args) => {
    const now = Date.now()
    return await ctx.db.insert('meetings', {
      consentConfirmedAt: now,
      consentText: args.consentText,
      consentVersion: args.consentVersion,
      createdAt: now,
      listenerProvider: 'meetingbaas',
      meetingUrl: args.meetingUrl,
      status: 'created',
      title: args.title,
      transcriptionProvider: 'assemblyai',
      updatedAt: now,
      userId: args.userId,
    })
  },
})

export const setBotId = internalMutation({
  args: {
    botId: v.string(),
    meetingId: v.id('meetings'),
  },
  handler: async (ctx, { botId, meetingId }) => {
    const meeting = await ctx.db.get(meetingId)
    if (!meeting) notFound({ entity: 'Meeting', id: meetingId })
    await ctx.db.patch(meetingId, {
      botId,
      status: 'dispatching_listener',
      updatedAt: Date.now(),
    })
  },
})

export const setNotesStatus = internalMutation({
  args: {
    error: v.optional(v.string()),
    meetingId: v.id('meetings'),
    status: v.union(
      v.literal('pending'),
      v.literal('generating'),
      v.literal('success'),
      v.literal('no_transcript'),
      v.literal('failed'),
    ),
  },
  handler: async (ctx, { error, meetingId, status }) => {
    await ctx.db.patch(meetingId, {
      notesError: error,
      notesStatus: status,
      updatedAt: Date.now(),
    })
  },
})

export const cascadeDelete = internalMutation({
  args: {
    meetingId: v.id('meetings'),
    userId: v.id('users'),
  },
  handler: async (ctx, { meetingId, userId }) => {
    const meeting = await ctx.db.get(meetingId)
    if (!meeting || meeting.userId !== userId) return { deleted: 0 }

    const turns = await ctx.db
      .query('meetingTranscriptTurns')
      .withIndex('by_meeting_turnOrder', (q) => q.eq('meetingId', meetingId))
      .collect()
    for (const t of turns) await ctx.db.delete(t._id)

    const note = await ctx.db
      .query('meetingNotes')
      .withIndex('by_meeting', (q) => q.eq('meetingId', meetingId))
      .unique()
    if (note) await ctx.db.delete(note._id)

    await ctx.db.delete(meetingId)
    return { deleted: turns.length + (note ? 1 : 0) + 1 }
  },
})

export const markCancelled = internalMutation({
  args: {
    meetingId: v.id('meetings'),
    reason: v.optional(v.string()),
  },
  handler: async (ctx, { meetingId, reason }) => {
    const meeting = await ctx.db.get(meetingId)
    if (!meeting) notFound({ entity: 'Meeting', id: meetingId })
    const now = Date.now()
    await ctx.db.patch(meetingId, {
      endedAt: now,
      failedAt: reason ? now : undefined,
      failureReason: reason,
      status: reason ? 'failed' : 'ended',
      updatedAt: now,
    })
  },
})
