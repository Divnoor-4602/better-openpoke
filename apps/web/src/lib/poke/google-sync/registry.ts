// Maps execution-agent Google tool calls onto local TanStack cache patches.
// When the agent successfully invokes one of these tools (server-confirmed
// via `tool.output.available` on the agent-event stream), the corresponding
// entry tells useGoogleSync (a) which cache key to mutate and (b) what to
// merge in. Add new entries here as Gmail/Calendar widgets gain server-side
// state mirroring (e.g. calendar_delete_event when the calendar widget
// ships).

import { calendarEventKeys } from '../calendar'
import { gmailDraftKeys } from '../gmail'

export type GoogleSyncEntry = {
  // Returns the TanStack cache key to patch, or null if the tool input is
  // missing the identifier we need (defensive — the LLM occasionally omits
  // required args; we'd rather no-op than throw inside a render-time effect).
  keyFn: (input: unknown) => null | readonly unknown[]

  // Returns the partial object to merge into the cached value. Receives the
  // tool input AND output so handlers can capture server-confirmed fields
  // (e.g. a rotated draftId or a delivered messageId).
  patch: (input: unknown, output: unknown) => Record<string, unknown>
}

const getDraftId = (input: unknown): null | string => {
  if (!input || typeof input !== 'object') return null
  const draftId = (input as { draft_id?: unknown }).draft_id
  return typeof draftId === 'string' && draftId ? draftId : null
}

const getEventId = (input: unknown): null | string => {
  if (!input || typeof input !== 'object') return null
  const eventId = (input as { event_id?: unknown }).event_id
  return typeof eventId === 'string' && eventId ? eventId : null
}

// Editable fields the agent might patch — keep in sync with
// CalendarEventPatch in catalog/schemas.ts. Anything not on this list is
// dropped from the optimistic cache update (so we don't surface fields
// the widget doesn't render or that aren't actually editable).
const CALENDAR_PATCHABLE_KEYS: ReadonlySet<string> = new Set([
  'attendees',
  'description',
  'summary',
])

const calendarPatchFromInput = (input: unknown): Record<string, unknown> => {
  if (!input || typeof input !== 'object') return {}
  const out: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(input as Record<string, unknown>)) {
    if (CALENDAR_PATCHABLE_KEYS.has(key) && value !== undefined) {
      out[key] = value
    }
  }
  return out
}

export const GOOGLE_SYNC_REGISTRY: Record<string, GoogleSyncEntry> = {
  // Execution-agent tool that calls GOOGLESUPER_DELETE_EVENT via Composio.
  // Flip status to 'discarded' so the widget's footer / action surface
  // collapses to the terminal state.
  calendar_delete_event: {
    keyFn: (input) => {
      const eventId = getEventId(input)
      return eventId ? calendarEventKeys.byId(eventId) : null
    },
    patch: () => ({ status: 'discarded' }),
  },
  // Execution-agent tool that calls GOOGLESUPER_PATCH_EVENT via Composio.
  // On success, mirror the editable fields the agent patched into the
  // widget's cache so the user sees the change without a refresh, and
  // flip status to 'updated' for the brief confirmation UI.
  calendar_update_event: {
    keyFn: (input) => {
      const eventId = getEventId(input)
      return eventId ? calendarEventKeys.byId(eventId) : null
    },
    patch: (input) => ({ ...calendarPatchFromInput(input), status: 'updated' }),
  },
  // Execution-agent tool that calls GOOGLESUPER_DELETE_DRAFT via Composio.
  // On success the Gmail resource is gone — flip the UI to "discarded"
  // (footer Send button becomes outline "Discarded", Open-in-Gmail link
  // hides — see email-footer.tsx).
  gmail_delete_draft: {
    keyFn: (input) => {
      const draftId = getDraftId(input)
      return draftId ? gmailDraftKeys.byId(draftId) : null
    },
    patch: () => ({ status: 'discarded' }),
  },
  // Execution-agent tool that calls GOOGLESUPER_SEND_DRAFT via Composio.
  // On success the draft has left Gmail — flip the UI to terminal "sent"
  // so the user can't click Send a second time.
  gmail_execute_draft: {
    keyFn: (input) => {
      const draftId = getDraftId(input)
      return draftId ? gmailDraftKeys.byId(draftId) : null
    },
    patch: () => ({ status: 'sent' }),
  },
}
