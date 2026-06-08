import type { HTMLMotionProps } from 'motion/react'

import { TrashIcon } from '@phosphor-icons/react'

import GoogleMeetIcon from '@/assets/google-meet-icon'
import { ChipButton } from '@general-poke/ui/components/chip-button'
import { CopyButton } from '@general-poke/ui/components/copy-button'

import { formatEventForClipboard } from './format-event-time'

type CalendarEventFooterProps = {
  attendees?: string[]
  description?: string
  endDatetime?: string
  location?: string
  meetLink?: string
  onDiscardAll?: () => void
  recurrence?: null | readonly string[]
  startDatetime?: string
  summary?: string
  terminal?: boolean
  timezone?: string
}

export const CalendarEventFooter = ({
  attendees,
  description,
  endDatetime,
  location,
  meetLink,
  onDiscardAll,
  recurrence,
  startDatetime,
  summary,
  terminal = false,
  timezone,
}: CalendarEventFooterProps) => {
  const isRecurring = Boolean(recurrence && recurrence.length > 0)

  if (terminal) {
    return (
      <div className="mt-10 flex items-center justify-end">
        <span className="text-xs font-light text-muted-foreground">
          Event cancelled
        </span>
      </div>
    )
  }

  const clipboardText = formatEventForClipboard({
    attendees,
    description,
    end_datetime: endDatetime,
    location,
    recurrence,
    start_datetime: startDatetime,
    summary,
    timezone,
  })

  return (
    <div className="mt-10 flex items-center">
      <div className="flex w-full items-center justify-between">
        <div className="flex items-center gap-2">
          {meetLink && <CalendarEventJoinMeetButton href={meetLink} />}
        </div>
        <div className="flex items-center gap-2">
          <CopyButton
            ariaLabelCopied="Copied event"
            ariaLabelIdle="Copy event"
            text={clipboardText}
          />
          {isRecurring && (
            <CalendarEventDiscardAllButton
              disabled={!onDiscardAll}
              onClick={onDiscardAll}
            />
          )}
        </div>
      </div>
    </div>
  )
}

type CalendarEventJoinMeetButtonProps = HTMLMotionProps<'button'> & {
  href: string
}

export const CalendarEventJoinMeetButton = ({
  href,
  ...props
}: CalendarEventJoinMeetButtonProps) => {
  return (
    <ChipButton
      onClick={() => window.open(href, '_blank', 'noopener,noreferrer')}
      {...props}
    >
      <div className="flex items-center gap-1">
        <GoogleMeetIcon className="h-3 w-auto" />
        <span>Join Meet</span>
      </div>
    </ChipButton>
  )
}

type CalendarEventDiscardAllButtonProps = HTMLMotionProps<'button'>

export const CalendarEventDiscardAllButton = (
  props: CalendarEventDiscardAllButtonProps,
) => {
  return (
    <ChipButton
      className="border-destructive/30 text-destructive hover:bg-destructive/10 hover:text-destructive"
      {...props}
    >
      <div className="flex items-center gap-1">
        <TrashIcon className="h-3 w-auto" />
        <span>Discard all events</span>
      </div>
    </ChipButton>
  )
}
