import type { QueryClient } from '@tanstack/react-query'

import { CalendarBlankIcon } from '@phosphor-icons/react'
import { useQueryClient } from '@tanstack/react-query'
import { createElement } from 'react'
import { toast } from 'sonner'

import type {
  CalendarEventCacheValue,
  CalendarEventPatch,
} from '@/lib/poke/calendar'

import { useMountEffect } from '@/hooks/use-mount-effect'
import { calendarEventKeys, useUpdateCalendarEvent } from '@/lib/poke/calendar'

import {
  formatEventDay,
  formatEventTimeRange,
  formatTimezoneShort,
} from '../format-event-time'

const TOAST_DEBOUNCE_MS = 1500

type Burst = {
  firstPrevious: CalendarEventCacheValue
  pendingTimer: null | ReturnType<typeof setTimeout>
  toastId: null | number | string
  touchedFields: Set<keyof CalendarEventPatch>
}

const bursts = new Map<string, Burst>()

export function useCalendarEventUpdateToast(eventId: string) {
  const queryClient = useQueryClient()
  const updateMutation = useUpdateCalendarEvent(eventId)

  useMountEffect(() => () => {
    const burst = bursts.get(eventId)
    if (burst?.pendingTimer) clearTimeout(burst.pendingTimer)
    bursts.delete(eventId)
  })

  return (patch: CalendarEventPatch) => {
    let burst = bursts.get(eventId)
    if (!burst) {
      const previous = queryClient.getQueryData<CalendarEventCacheValue>(
        calendarEventKeys.byId(eventId),
      )
      if (!previous) {
        // No cache entry — bail to a fire-and-forget mutation without toast.
        updateMutation.mutate(patch)
        return
      }
      burst = {
        firstPrevious: previous,
        pendingTimer: null,
        toastId: null,
        touchedFields: new Set(),
      }
      bursts.set(eventId, burst)
    }
    for (const key of Object.keys(patch)) {
      burst.touchedFields.add(key as keyof CalendarEventPatch)
    }

    updateMutation.mutate(patch, {
      onSuccess: () => {
        const current = bursts.get(eventId)
        if (!current) return
        if (current.pendingTimer) clearTimeout(current.pendingTimer)
        current.pendingTimer = setTimeout(() => {
          emitToast(eventId, queryClient, updateMutation)
        }, TOAST_DEBOUNCE_MS)
      },
    })
  }
}

const emitToast = (
  eventId: string,
  queryClient: QueryClient,
  updateMutation: ReturnType<typeof useUpdateCalendarEvent>,
) => {
  const burst = bursts.get(eventId)
  if (!burst) return

  const current = queryClient.getQueryData<CalendarEventCacheValue>(
    calendarEventKeys.byId(eventId),
  )

  const undoPatch: CalendarEventPatch = {}
  for (const key of burst.touchedFields) {
    const previousValue =
      burst.firstPrevious[key as keyof CalendarEventCacheValue]
    if (previousValue !== undefined) {
      ;(undoPatch[key] as unknown) = previousValue
      continue
    }

    ;(undoPatch[key] as unknown) = emptyValueForField(key)
  }

  const description = current ? describeEvent(current) : undefined

  bursts.delete(eventId)

  toast('Event has been updated', {
    action: {
      label: 'Undo',
      onClick: () => {
        updateMutation.mutate(undoPatch)
      },
    },
    description,
    icon: createElement(CalendarBlankIcon, { className: 'size-4' }),
  })
}

const emptyValueForField = (
  key: keyof CalendarEventPatch,
): CalendarEventPatch[keyof CalendarEventPatch] => {
  switch (key) {
    case 'attendees':
      return []
    case 'description':
    case 'summary':
      return ''
    default: {
      const _unhandled: never = key
      return _unhandled
    }
  }
}

const describeEvent = (event: CalendarEventCacheValue): string => {
  if (!event.start_datetime) return event.summary ?? 'Untitled event'
  const day = formatEventDay(event.start_datetime, event.timezone)
  const range = event.end_datetime
    ? formatEventTimeRange(
        event.start_datetime,
        event.end_datetime,
        event.timezone,
      )
    : null
  const tz = range ? formatTimezoneShort(event.timezone) : null
  const parts = [day, range, tz].filter(Boolean)
  return parts.join(' · ')
}
