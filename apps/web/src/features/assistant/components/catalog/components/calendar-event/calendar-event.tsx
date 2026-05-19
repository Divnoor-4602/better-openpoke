import { useState } from 'react'

import { useDebouncedCallback } from '@/hooks/use-debounce-hook'

import type {
  CalendarCreateEventInput,
  CalendarEventPatch,
} from '../../schemas'
import type { CalendarEventDiscardButtonProps } from './calendar-discard-button'

import { CalendarEventDateTime } from './calendar-date-time'
import { CalendarEventFooter } from './calendar-footer'
import { CalendarEventFrequencyBadge } from './calendar-frequency-badge'
import {
  CalendarEventContent,
  CalendarEventHeader,
  CalendarEventShell,
} from './calendar-layout'
import { CalendarEventLocation } from './calendar-location'
import { CalendarEventParticipants } from './calendar-participants'

export type CalendarEventActions = {
  discard?: CalendarEventDiscardButtonProps
  onDiscardAll?: () => void
  onReschedule?: () => void
  status?: 'discarded' | 'idle' | 'updated' | 'updating'
  update: (patch: CalendarEventPatch) => void
}

const TEXT_DEBOUNCE_MS = 800

type CalendarEventProps = CalendarCreateEventInput & {
  actions?: CalendarEventActions
}

export const CalendarEvent = ({ actions, ...props }: CalendarEventProps) => {
  const editable = Boolean(actions)
  const terminal = actions?.status === 'discarded'
  const attendees = props.attendees ?? []

  const meetLink = props.meet_link

  const debouncedUpdate = useDebouncedCallback(
    (patch: CalendarEventPatch) => actions?.update(patch),
    TEXT_DEBOUNCE_MS,
  )

  const handleAddAttendee = (email: string) => {
    const trimmed = email.trim()
    if (!trimmed || attendees.includes(trimmed)) return
    actions?.update({ attendees: [...attendees, trimmed] })
  }

  const handleRemoveAttendee = (index: number) => {
    actions?.update({
      attendees: attendees.filter((_, i) => i !== index),
    })
  }

  return (
    <CalendarEventShell>
      <CalendarEventHeader discard={actions?.discard} />
      <CalendarEventContent>
        <div className="flex items-start justify-between gap-3">
          <SummaryField
            disabled={terminal}
            editable={editable}
            onChange={(value) => debouncedUpdate({ summary: value })}
            summary={props.summary}
          />
          <CalendarEventFrequencyBadge recurrence={props.recurrence} />
        </div>
        <DescriptionField
          description={props.description}
          disabled={terminal}
          editable={editable}
          onChange={(value) => debouncedUpdate({ description: value })}
        />
        <CalendarEventDateTime
          disabled={terminal}
          end={props.end_datetime}
          onReschedule={actions?.onReschedule}
          start={props.start_datetime}
          timezone={props.timezone}
        />
        <CalendarEventParticipants
          attendees={attendees}
          disabled={terminal}
          onAdd={editable ? handleAddAttendee : undefined}
          onRemove={editable ? handleRemoveAttendee : undefined}
        />
        <CalendarEventLocation location={props.location} />
        <CalendarEventFooter
          attendees={attendees}
          description={props.description}
          endDatetime={props.end_datetime}
          location={props.location}
          meetLink={meetLink}
          onDiscardAll={actions?.onDiscardAll}
          recurrence={props.recurrence}
          startDatetime={props.start_datetime}
          summary={props.summary}
          terminal={terminal}
          timezone={props.timezone}
        />
      </CalendarEventContent>
    </CalendarEventShell>
  )
}

type SummaryFieldProps = {
  disabled: boolean
  editable: boolean
  onChange: (value: string) => void
  summary?: string
}

const SummaryField = (props: SummaryFieldProps) => {
  if (!props.editable) {
    return <span className="text-sm font-normal">{props.summary ?? ''}</span>
  }

  return <SummaryEditor {...props} key={props.summary ?? ''} />
}

const SummaryEditor = ({
  disabled,
  onChange,
  summary = '',
}: SummaryFieldProps) => {
  const [value, setValue] = useState(summary)
  return (
    <input
      aria-label="Event title"
      className="w-full min-w-0 flex-1 bg-transparent text-sm font-normal outline-none ring-0 placeholder:text-muted-foreground focus:outline-none focus:ring-0 focus-visible:outline-none focus-visible:ring-0 disabled:cursor-not-allowed disabled:opacity-60"
      disabled={disabled}
      onChange={(event) => {
        setValue(event.target.value)
        onChange(event.target.value)
      }}
      placeholder="Event title"
      value={value}
    />
  )
}

type DescriptionFieldProps = {
  description?: string
  disabled: boolean
  editable: boolean
  onChange: (value: string) => void
}

const DescriptionField = (props: DescriptionFieldProps) => {
  if (!props.editable) {
    if (!props.description) return null
    return (
      <div className="mt-3">
        <span className="text-xs font-normal text-muted-foreground">
          {props.description}
        </span>
      </div>
    )
  }
  return <DescriptionEditor {...props} key={props.description ?? ''} />
}

const DescriptionEditor = ({
  description = '',
  disabled,
  onChange,
}: DescriptionFieldProps) => {
  const [value, setValue] = useState(description)
  return (
    <textarea
      aria-label="Event description"
      className="mt-3 w-full resize-none bg-transparent text-xs font-normal leading-relaxed text-muted-foreground outline-none ring-0 placeholder:text-muted-foreground focus:outline-none focus:ring-0 focus-visible:outline-none focus-visible:ring-0 disabled:cursor-not-allowed disabled:opacity-60"
      disabled={disabled}
      onChange={(event) => {
        setValue(event.target.value)
        onChange(event.target.value)
      }}
      placeholder="Add a description"
      rows={3}
      value={value}
    />
  )
}
