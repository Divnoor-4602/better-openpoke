import { internal } from '../_generated/api'
import { internalMutation } from '../_generated/server'

const STUCK_THRESHOLD_MS = 30 * 60 * 1000

// Marks meetings stuck in a non-terminal pre-recording state for more than
// 30 minutes as failed. Prevents abandoned meetings (bot never joined,
// MB callbacks lost, etc.) from sitting forever.
export const failStuckMeetings = internalMutation({
  args: {},
  handler: async (ctx) => {
    const cutoff = Date.now() - STUCK_THRESHOLD_MS
    const candidates = await ctx.db
      .query('meetings')
      .withIndex('by_user_status')
      .filter((q) =>
        q.or(
          q.eq(q.field('status'), 'created'),
          q.eq(q.field('status'), 'dispatching_listener'),
          q.eq(q.field('status'), 'listener_joining'),
        ),
      )
      .collect()

    let failed = 0
    for (const meeting of candidates) {
      if (meeting.createdAt < cutoff) {
        await ctx.db.patch(meeting._id, {
          failedAt: Date.now(),
          failureReason: 'stuck_before_recording',
          notesStatus: 'no_transcript',
          status: 'failed',
          updatedAt: Date.now(),
        })
        await ctx.runMutation(internal.audit_event.mutations.log, {
          action: 'meeting.ended',
          entityId: meeting._id,
          entityType: 'meeting',
          metadata: { status: 'failed' },
          userId: meeting.userId,
        })
        failed += 1
      }
    }
    return { failed }
  },
})
