import type { HTMLMotionProps } from 'motion/react'

import { ChipButton } from '@general-poke/ui/components/chip-button'
import { ArrowBendUpRightIcon, MoonIcon, SunIcon } from '@phosphor-icons/react'

import {
  formatEventDay,
  formatEventTimeRange,
  formatTimezoneShort,
  isDaytime,
} from './format-event-time'

type CalendarEventDateTimeProps = {
  disabled?: boolean
  end?: string
  onReschedule?: () => void
  start?: string
  timezone?: string
}

export const CalendarEventDateTime = ({
  disabled,
  end,
  onReschedule,
  start,
  timezone,
}: CalendarEventDateTimeProps) => {
  if (!start) return null

  const day = formatEventDay(start, timezone)
  const timeRange = end ? formatEventTimeRange(start, end, timezone) : null
  const tzLabel = timeRange ? formatTimezoneShort(timezone) : null
  const TimeOfDayIcon = isDaytime(start, timezone) ? SunIcon : MoonIcon

  return (
    <div className="mt-4 flex items-center justify-between">
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-1">
          <TimeOfDayIcon className="size-3" />
          <span className="text-xs font-light">{day}</span>
        </div>
        {timeRange && (
          <div className="flex items-center gap-2">
            <span className="text-xs font-normal">{timeRange}</span>
            {tzLabel && <span className="text-xs font-normal">{tzLabel}</span>}
          </div>
        )}
      </div>
      <CalendarEventRescheduleButton
        disabled={disabled || !onReschedule}
        onClick={onReschedule}
      />
    </div>
  )
}

type CalendarEventRescheduleButtonProps = HTMLMotionProps<'button'>

export const CalendarEventRescheduleButton = (
  props: CalendarEventRescheduleButtonProps,
) => {
  return (
    <ChipButton {...props}>
      <div className="flex items-center gap-1">
        <ArrowBendUpRightIcon className="h-3 w-auto" />
        <span>Reschedule</span>
      </div>
    </ChipButton>
  )
}
