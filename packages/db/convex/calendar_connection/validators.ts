import type { Infer } from 'convex/values'

import { Table } from 'convex-helpers/server'
import { v } from 'convex/values'

import { User } from '../user/validators'

export const vCalendarProvider = v.union(v.literal('google'))

export const vCalendarConnectionStatus = v.union(
  v.literal('active'),
  v.literal('revoked'),
  v.literal('error'),
  v.literal('permission_denied'),
)

export const vCalendarConnection = v.object({
  accountEmail: v.string(),
  autoJoinEnabled: v.boolean(),
  connectedAt: v.number(),
  mbCalendarId: v.string(),
  provider: vCalendarProvider,
  rawCalendarId: v.string(),
  status: vCalendarConnectionStatus,
  updatedAt: v.number(),
  userId: User._id,
})

export const CalendarConnection = Table(
  'calendarConnections',
  vCalendarConnection.fields,
)

export type TCalendarConnection = Infer<typeof CalendarConnection.doc>
export type TCalendarConnectionId = Infer<typeof CalendarConnection._id>
export type TCalendarConnectionStatus = Infer<typeof vCalendarConnectionStatus>
export type TCalendarProvider = Infer<typeof vCalendarProvider>
