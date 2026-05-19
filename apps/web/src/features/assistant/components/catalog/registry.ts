import type { CatalogEntry } from './types'

import { fromInput } from './from-input'
import { zCalendarCreateEventInput, zSendDraftInput } from './schemas'
import { CalendarEventWidget } from './widgets/calendar-event-widget'
import { DraftEmailWidget } from './widgets/draft-email-widget'

const extractCalendarOutput = (
  output: unknown,
): { event_id?: string; meet_link?: string } => {
  if (!output || typeof output !== 'object') return {}
  const root = output as Record<string, unknown>
  const data = (root.data as Record<string, unknown> | undefined) ?? root
  const inner =
    (data?.response_data as Record<string, unknown> | undefined) ?? data
  const result: { event_id?: string; meet_link?: string } = {}
  const id = inner?.id ?? inner?.event_id
  if (typeof id === 'string' && id) result.event_id = id

  const meet = inner?.hangoutLink ?? inner?.hangout_link ?? inner?.meet_link
  if (typeof meet === 'string' && meet) result.meet_link = meet
  return result
}

export const CATALOG = {
  calendar_create_event: {
    Component: fromInput(CalendarEventWidget, zCalendarCreateEventInput, {
      mapOutput: extractCalendarOutput,
    }),
    placement: 'block',
  },
  send_draft: {
    Component: fromInput(DraftEmailWidget, zSendDraftInput),
    placement: 'block',
  },
} as const satisfies Record<string, CatalogEntry>

export type CatalogToolName = keyof typeof CATALOG

export const CATALOG_TOOL_NAMES: ReadonlySet<string> = new Set(
  Object.keys(CATALOG),
)

export const getCatalogEntry = (toolName: string): CatalogEntry | undefined =>
  (CATALOG as Record<string, CatalogEntry>)[toolName]

export const hasCatalogRenderer = (toolName: string): boolean =>
  CATALOG_TOOL_NAMES.has(toolName)
