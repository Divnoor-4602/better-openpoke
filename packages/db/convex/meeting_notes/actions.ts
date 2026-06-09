import { v } from 'convex/values'

import { internal } from '../_generated/api'
import { internalAction } from '../_generated/server'
import { legalAgent } from '../integrations/agent/base'

const SUMMARY_PROMPT = [
  'You are summarizing a legal meeting transcript. Speaker labels (A, B, C, …) are placeholders — do not invent names.',
  'Return well-structured markdown notes with the following sections, each as an H1 heading prefixed with "# ":',
  '',
  '# Testing Overview',
  '- Bulleted summary of the meeting context.',
  '',
  '# Key Discussion Points',
  '- Bulleted list of important topics discussed.',
  '',
  '# Action Items',
  '- Bulleted list of action items (or "None" if none).',
  '',
  '# Open Questions',
  '- Bulleted list of follow-ups (or "None").',
  '',
  'Use only markdown. No preamble, no closing remarks.',
].join('\n')

export const generate = internalAction({
  args: {
    meetingId: v.id('meetings'),
    userId: v.id('users'),
  },
  handler: async (ctx, { meetingId, userId }) => {
    await ctx.runMutation(internal.meeting.mutations.setNotesStatus, {
      meetingId,
      status: 'generating',
    })

    const transcript = await ctx.runQuery(
      internal.meeting.queries.getTranscriptText,
      { meetingId, userId },
    )
    if (!transcript) {
      console.log('[generate-notes] no transcript', { meetingId })
      await ctx.runMutation(internal.meeting.mutations.setNotesStatus, {
        meetingId,
        status: 'no_transcript',
      })
      return { generated: false as const, reason: 'no_transcript' as const }
    }

    try {
      const title = transcript.title ?? `Meeting ${meetingId}`
      const prompt = `${SUMMARY_PROMPT}\n\nMeeting title: ${title}\n\nTranscript:\n${transcript.transcript}`

      const { thread } = await legalAgent.createThread(ctx, { title, userId })
      const result = await thread.generateText({ prompt })

      const noteId = await ctx.runMutation(
        internal.meeting_notes.mutations.upsertForMeeting,
        {
          content: result.text,
          meetingId,
          title,
          userId,
        },
      )

      await ctx.runMutation(internal.meeting.mutations.setNotesStatus, {
        meetingId,
        status: 'success',
      })

      await ctx.runMutation(internal.audit_event.mutations.log, {
        action: 'notes.generated',
        entityId: noteId,
        entityType: 'meeting_notes',
        userId,
      })

      console.log('[generate-notes] saved', {
        contentLength: result.text.length,
        meetingId,
        noteId,
      })
      return { generated: true as const }
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err)
      console.error('[generate-notes] failed', {
        meetingId,
        reason: message.slice(0, 200),
      })
      await ctx.runMutation(internal.meeting.mutations.setNotesStatus, {
        error: message.slice(0, 300),
        meetingId,
        status: 'failed',
      })
      return { generated: false as const, reason: 'failed' as const }
    }
  },
})
