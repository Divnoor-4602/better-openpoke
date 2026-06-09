import { v } from 'convex/values'

import { api, internal } from '../../_generated/api'
import { pokeAction, pokeMutation } from '../../auth'
import { notFound, validationError } from '../../error'

export const updateNote = pokeMutation({
  args: {
    content: v.optional(v.string()),
    noteId: v.id('meetingNotes'),
    title: v.optional(v.string()),
  },
  handler: async (ctx, { content, noteId, title }) => {
    const note = await ctx.db.get(noteId)
    if (!note) notFound({ entity: 'MeetingNotes', id: noteId })
    if (note.userId !== ctx.user._id) {
      validationError({ entity: 'MeetingNotes', message: 'Not authorized' })
    }

    const patch: { content?: string; title?: string; updatedAt: number } = {
      updatedAt: Date.now(),
    }
    if (content !== undefined) patch.content = content
    if (title !== undefined) patch.title = title
    await ctx.db.patch(noteId, patch)

    await ctx.runMutation(internal.audit_event.mutations.log, {
      action: 'notes.updated',
      entityId: noteId,
      entityType: 'meeting_notes',
      userId: ctx.user._id,
    })

    return { ok: true as const }
  },
})

export const deleteNote = pokeMutation({
  args: { noteId: v.id('meetingNotes') },
  handler: async (ctx, { noteId }) => {
    const note = await ctx.db.get(noteId)
    if (!note) notFound({ entity: 'MeetingNotes', id: noteId })
    if (note.userId !== ctx.user._id) {
      validationError({ entity: 'MeetingNotes', message: 'Not authorized' })
    }
    await ctx.db.delete(noteId)
    await ctx.runMutation(internal.audit_event.mutations.log, {
      action: 'notes.deleted',
      entityId: noteId,
      entityType: 'meeting_notes',
      userId: ctx.user._id,
    })
    return { ok: true as const }
  },
})

export const regenerateForMeeting = pokeAction({
  args: { meetingId: v.id('meetings') },
  handler: async (ctx, { meetingId }) => {
    const user = await ctx.runQuery(api.public.user.queries.me, {})
    return await ctx.runAction(internal.meeting_notes.actions.generate, {
      meetingId,
      userId: user._id,
    })
  },
})
