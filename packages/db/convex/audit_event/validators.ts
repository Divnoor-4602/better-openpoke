import type { Infer } from 'convex/values'

import { Table } from 'convex-helpers/server'
import { v } from 'convex/values'

import { User } from '../user/validators'

export const vAuditAction = v.union(
  v.literal('meeting.consent.recorded'),
  v.literal('meeting.created'),
  v.literal('meeting.ended'),
  v.literal('meeting.deleted'),
  v.literal('notes.generated'),
  v.literal('notes.updated'),
  v.literal('notes.deleted'),
  v.literal('autojoin.enabled'),
  v.literal('autojoin.disabled'),
  v.literal('calendar.connected'),
  v.literal('calendar.disconnected'),
)

export const vAuditEvent = v.object({
  action: vAuditAction,
  createdAt: v.number(),
  entityId: v.optional(v.string()),
  entityType: v.optional(v.string()),
  metadata: v.optional(
    v.object({
      consentVersion: v.optional(v.string()),
      externalEventId: v.optional(v.string()),
      meetingUrl: v.optional(v.string()),
      status: v.optional(v.string()),
    }),
  ),
  userId: User._id,
})

export const AuditEvent = Table('auditEvents', vAuditEvent.fields)

export type TAuditAction = Infer<typeof vAuditAction>
export type TAuditEvent = Infer<typeof AuditEvent.doc>
export type TAuditEventId = Infer<typeof AuditEvent._id>
