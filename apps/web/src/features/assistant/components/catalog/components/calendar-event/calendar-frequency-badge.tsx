import { CalendarBlankIcon, RepeatIcon } from '@phosphor-icons/react'

import { formatRecurrence } from './format-recurrence'

type CalendarEventFrequencyBadgeProps = {
  recurrence?: null | readonly string[]
}

export const CalendarEventFrequencyBadge = ({
  recurrence,
}: CalendarEventFrequencyBadgeProps) => {
  const isRecurring = Boolean(recurrence && recurrence.length > 0)
  const label = formatRecurrence(recurrence)
  const Icon = isRecurring ? RepeatIcon : CalendarBlankIcon

  return (
    <div className="flex w-fit items-center gap-1 rounded-poke border border-blue-200 bg-blue-50 px-2 py-0.5">
      <Icon className="size-3" />
      <span className="text-xs font-light">{label}</span>
    </div>
  )
}
