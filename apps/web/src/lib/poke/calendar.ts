import type {
  CalendarEventDiscardResponse,
  CalendarEventUpdateResponse,
} from '@openpoke/sdk'

import { useQuery, useQueryClient } from '@tanstack/react-query'

import type { CalendarEventPatch } from '@/features/assistant/components/catalog/schemas'

import { useOptimisticMutation } from '@/features/assistant/components/catalog/hooks/use-optimistic-mutation'
import { stripUndefined } from '@/lib/utils'

import { poke } from './client'

export type { CalendarEventPatch } from '@/features/assistant/components/catalog/schemas'

export const calendarEventKeys = {
  all: ['calendar', 'events'] as const,
  byId: (eventId: string) => [...calendarEventKeys.all, eventId],
}

export const calendarEventMutationKeys = {
  discard: (eventId: string) => [...calendarEventKeys.byId(eventId), 'discard'],
  update: (eventId: string) => [...calendarEventKeys.byId(eventId), 'update'],
}

export type CalendarEventCacheValue = {
  attendees?: string[]
  calendar_id?: string
  create_meeting_room?: boolean
  description?: string
  end_datetime?: string
  eventId: string
  location?: string
  meet_link?: string
  recurrence?: string[]
  start_datetime?: string
  status: 'discarded' | 'idle' | 'updated' | 'updating'
  summary?: string
  timezone?: string
}

export type CalendarEventEditableFields = CalendarEventPatch

export function useCalendarEvent(
  eventId: string,
  initial: CalendarEventCacheValue,
) {
  const queryClient = useQueryClient()
  const queryKey = calendarEventKeys.byId(eventId)
  // Seed under any cache value useGoogleSync wrote before mount. Read
  // only — the render-time setQueryData we had here notified subscribers
  // and re-rendered in a loop. React Compiler memoizes `seeded`; TanStack
  // ignores `initialData` once a value is cached.
  const existing =
    queryClient.getQueryData<Partial<CalendarEventCacheValue>>(queryKey)
  const seeded: CalendarEventCacheValue = { ...initial, ...(existing ?? {}) }
  return useQuery<CalendarEventCacheValue>({
    gcTime: Infinity,
    initialData: seeded,
    queryFn: () => Promise.resolve(seeded),
    queryKey,
    staleTime: Infinity,
  })
}

export function useDiscardCalendarEvent(eventId: string) {
  return useOptimisticMutation<
    CalendarEventCacheValue,
    CalendarEventDiscardResponse
  >({
    mutationFn: async () => {
      const { data } = await poke.calendar.events.discard({ eventId })
      return data
    },
    mutationKey: calendarEventMutationKeys.discard(eventId),
    optimistic: () => ({ status: 'discarded' }),
    queryKey: calendarEventKeys.byId(eventId),
  })
}

export function useUpdateCalendarEvent(eventId: string) {
  return useOptimisticMutation<
    CalendarEventCacheValue,
    CalendarEventUpdateResponse,
    CalendarEventEditableFields
  >({
    mutationFn: async (fields) => {
      const { data } = await poke.calendar.events.update({
        eventId,
        ...stripUndefined(fields),
      })
      return data
    },
    mutationKey: calendarEventMutationKeys.update(eventId),

    onSuccess: (response) => ({
      eventId: response.eventId,
      status: 'updated',
    }),
    optimistic: (_previous, fields) => ({
      ...stripUndefined(fields),
      status: 'updating',
    }),
    queryKey: calendarEventKeys.byId(eventId),
  })
}
