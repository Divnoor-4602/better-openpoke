import { z } from 'zod'

export const CalendarEventStatusSchema = z.enum([
  'confirmed',
  'cancelled',
  'tentative',
])
export type CalendarEventStatus = z.infer<typeof CalendarEventStatusSchema>

export const CalendarMeetingPlatformSchema = z.enum(['zoom', 'meet', 'teams'])
export type CalendarMeetingPlatform = z.infer<
  typeof CalendarMeetingPlatformSchema
>

export const CalendarEventSchema = z.object({
  botScheduled: z.boolean(),
  endTime: z.string(),
  eventId: z.string(),
  isException: z.boolean(),
  meetingPlatform: CalendarMeetingPlatformSchema.nullable(),
  meetingUrl: z.string().nullable(),
  seriesId: z.string(),
  startTime: z.string(),
  status: CalendarEventStatusSchema,
  title: z.string(),
})
export type CalendarEvent = z.infer<typeof CalendarEventSchema>

export const CreateConnectionInputSchema = z.object({
  rawCalendarId: z.string().default('primary'),
  refreshToken: z.string(),
})
export type CreateConnectionInput = z.infer<typeof CreateConnectionInputSchema>

export const CreateConnectionOutputSchema = z.object({
  accountEmail: z.string(),
  mbCalendarId: z.string(),
})
export type CreateConnectionOutput = z.infer<
  typeof CreateConnectionOutputSchema
>

export const ListEventsInputSchema = z.object({
  mbCalendarId: z.string(),
  startAfter: z.string().optional(),
})
export type ListEventsInput = z.infer<typeof ListEventsInputSchema>

export const ListEventsOutputSchema = z.object({
  events: z.array(CalendarEventSchema),
})
export type ListEventsOutput = z.infer<typeof ListEventsOutputSchema>

export const ScheduleBotInputSchema = z.object({
  allOccurrences: z.boolean().default(false),
  botName: z.string().optional(),
  callbackUrl: z.string().url(),
  eventId: z.string(),
  listenerWsUrl: z.string(),
  mbCalendarId: z.string(),
  seriesId: z.string(),
  webhookSecret: z.string(),
})
export type ScheduleBotInput = z.infer<typeof ScheduleBotInputSchema>

export const ScheduleBotOutputSchema = z.object({
  scheduledEventIds: z.array(z.string()),
})
export type ScheduleBotOutput = z.infer<typeof ScheduleBotOutputSchema>

export const DeleteConnectionInputSchema = z.object({
  mbCalendarId: z.string(),
})
export type DeleteConnectionInput = z.infer<typeof DeleteConnectionInputSchema>

export const DeleteConnectionOutputSchema = z.object({
  mbCalendarId: z.string(),
  ok: z.literal(true),
})
export type DeleteConnectionOutput = z.infer<
  typeof DeleteConnectionOutputSchema
>

export const DeleteCalendarBotInputSchema = z.object({
  eventId: z.string(),
  mbCalendarId: z.string(),
})
export type DeleteCalendarBotInput = z.infer<
  typeof DeleteCalendarBotInputSchema
>

export const DeleteCalendarBotOutputSchema = z.object({
  eventId: z.string(),
  ok: z.literal(true),
})
export type DeleteCalendarBotOutput = z.infer<
  typeof DeleteCalendarBotOutputSchema
>
