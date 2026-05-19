import { CalendarBlankIcon } from '@phosphor-icons/react'
import { useQueryClient } from '@tanstack/react-query'
import { createElement, useRef } from 'react'
import { toast } from 'sonner'

import type { CalendarEventCacheValue } from '@/lib/poke/calendar'

import { calendarEventKeys, useDiscardCalendarEvent } from '@/lib/poke/calendar'

const DISCARD_GRACE_MS = 5000

export function useCalendarEventDiscard(eventId: string) {
  const queryClient = useQueryClient()
  const discardMutation = useDiscardCalendarEvent(eventId)
  const timerRef = useRef<null | ReturnType<typeof setTimeout>>(null)
  const previousRef = useRef<CalendarEventCacheValue | null>(null)

  const cancelGrace = () => {
    if (timerRef.current) {
      clearTimeout(timerRef.current)
      timerRef.current = null
    }
    if (previousRef.current) {
      queryClient.setQueryData(
        calendarEventKeys.byId(eventId),
        previousRef.current,
      )
      previousRef.current = null
    }
  }

  const discard = () => {
    const queryKey = calendarEventKeys.byId(eventId)
    const previous = queryClient.getQueryData<CalendarEventCacheValue>(queryKey)
    if (!previous) return

    if (timerRef.current) clearTimeout(timerRef.current)
    previousRef.current = previous
    queryClient.setQueryData<CalendarEventCacheValue>(queryKey, {
      ...previous,
      status: 'discarded',
    })

    timerRef.current = setTimeout(() => {
      timerRef.current = null
      previousRef.current = null
      discardMutation.mutate()
    }, DISCARD_GRACE_MS)

    toast('Event has been cancelled', {
      action: {
        label: 'Undo',
        onClick: cancelGrace,
      },
      description: previous.summary ?? undefined,
      duration: DISCARD_GRACE_MS,
      icon: createElement(CalendarBlankIcon, { className: 'size-4' }),
    })
  }

  return { discard }
}
