import { z } from 'zod'

const zSendDraftStrict = z.object({
  attachment: z
    .object({
      mimetype: z.string().optional(),
      name: z.string(),
      s3key: z.string().optional(),
    })
    .optional()
    .describe('Single attachment metadata for the draft.'),
  bcc: z
    .array(z.string())
    .optional()
    .describe('Optional BCC recipient emails.'),
  body: z.string().describe('Email body content (plain text).'),
  cc: z.array(z.string()).optional().describe('Optional CC recipient emails.'),
  draft_id: z
    .string()
    .optional()
    .describe('Created Gmail draft id, when available.'),
  extra_recipients: z
    .array(z.string())
    .optional()
    .describe('Additional primary recipient emails.'),
  is_html: z
    .boolean()
    .optional()
    .describe('True when the body contains HTML content.'),
  subject: z.string().describe('Email subject for the draft.'),
  thread_id: z
    .string()
    .optional()
    .describe('Existing Gmail thread id when this draft belongs to a thread.'),
  to: z.string().describe('Recipient email for the draft.'),
})

const zCalendarCreateEventStrict = z.object({
  attendees: z
    .array(z.string())
    .optional()
    .describe('Email addresses of attendees to invite.'),
  calendar_id: z
    .string()
    .optional()
    .describe("Calendar identifier, defaults to 'primary'."),
  create_meeting_room: z
    .boolean()
    .optional()
    .describe('Attach a Google Meet conference link to the event.'),
  description: z.string().optional().describe('Event description / body.'),
  end_datetime: z.string().describe('Event end (RFC3339).'),
  event_id: z
    .string()
    .optional()
    .describe('Created Google Calendar event id, when available.'),
  meet_link: z
    .string()
    .optional()
    .describe(
      'Google Meet URL (Google Calendar `hangoutLink`) when one is ' +
        'attached to the event. Populated from the create/patch response, ' +
        'not from the LLM input.',
    ),
  force_overlap: z
    .boolean()
    .optional()
    .describe(
      'Server-side override: skip the freebusy precheck and create the event ' +
        'even if it overlaps an existing one. Set true ONLY after the user has ' +
        'explicitly confirmed scheduling despite a known conflict. The UI ' +
        'ignores this field.',
    ),
  location: z
    .string()
    .optional()
    .describe('Physical or virtual location text.'),
  recurrence: z
    .array(z.string())
    .optional()
    .describe(
      'RRULE / EXRULE / RDATE / EXDATE lines per RFC 5545 for recurring events. ' +
        'Examples: ' +
        '["RRULE:FREQ=DAILY"] (daily), ' +
        '["RRULE:FREQ=WEEKLY;BYDAY=TU"] (weekly on Tue), ' +
        '["RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR"] (weekdays), ' +
        '["RRULE:FREQ=MONTHLY;BYDAY=1MO"] (first Mon of each month), ' +
        '["RRULE:FREQ=WEEKLY;BYDAY=TU;UNTIL=20260901T000000Z"] (weekly until Sep 1). ' +
        'Omit for one-off events.',
    ),
  send_updates: z
    .string()
    .optional()
    .describe("Notification policy: 'all', 'externalOnly', or 'none'."),
  start_datetime: z
    .string()
    .describe('Event start (RFC3339, e.g. 2025-06-01T15:00:00-07:00).'),
  summary: z.string().describe('Event title.'),
  timezone: z
    .string()
    .optional()
    .describe("IANA timezone, e.g. 'America/Los_Angeles'."),
})

export const TOOL_SCHEMAS = {
  calendar_create_event: {
    partial: zCalendarCreateEventStrict.partial(),
    strict: zCalendarCreateEventStrict,
  },
  send_draft: {
    partial: zSendDraftStrict.partial(),
    strict: zSendDraftStrict,
  },
} as const

export const zSendDraftInput = TOOL_SCHEMAS.send_draft.partial
export type SendDraftInput = z.infer<typeof zSendDraftInput>

// Editable subset of the LLM tool input, derived from the strict schema so
// the patch shape can't drift from the source of truth. Mirrors the server
// DraftUpdateRequest (to, subject, body, cc, bcc) and is what the widget
// validates against before calling the PATCH mutation.
export const zSendDraftPatch = zSendDraftStrict
  .pick({ bcc: true, body: true, cc: true, subject: true, to: true })
  .partial()
export type SendDraftPatch = z.infer<typeof zSendDraftPatch>

export const zCalendarCreateEventInput =
  TOOL_SCHEMAS.calendar_create_event.partial
export type CalendarCreateEventInput = z.infer<typeof zCalendarCreateEventInput>

// Editable subset for the UI PATCH path. Datetime / timezone / recurrence
// stay agent-only (datetime needs conflict awareness, recurrence has
// "this vs all instances" semantics — both belong in conversational flow).
// Location is read-only per product decision.
export const zCalendarEventPatch = zCalendarCreateEventStrict
  .pick({ attendees: true, description: true, summary: true })
  .partial()
export type CalendarEventPatch = z.infer<typeof zCalendarEventPatch>
