import type { CalendarEventCacheValue } from '@/lib/poke/calendar'

import { useCalendarEvent } from '@/lib/poke/calendar'

import type { CalendarCreateEventInput } from '../schemas'

import { useChatDraftStore } from '../../../store/chat-draft-store'
import { CalendarEvent } from '../components/calendar-event/calendar-event'
import { formatEventForClipboard } from '../components/calendar-event/format-event-time'
import { useCalendarEventDiscard } from '../components/calendar-event/hooks/use-calendar-event-discard'
import { useCalendarEventUpdateToast } from '../components/calendar-event/hooks/use-calendar-event-toasts'

export const CalendarEventWidget = (props: CalendarCreateEventInput) => {
  if (!props.event_id) return <CalendarEvent {...props} />
  return <CalendarEventWidgetActive eventId={props.event_id} initial={props} />
}

const CalendarEventWidgetActive = ({
  eventId,
  initial,
}: {
  eventId: string
  initial: CalendarCreateEventInput
}) => {
  const initialCache: CalendarEventCacheValue = {
    attendees: initial.attendees,
    calendar_id: initial.calendar_id,
    create_meeting_room: initial.create_meeting_room,
    description: initial.description,
    end_datetime: initial.end_datetime,
    eventId,
    location: initial.location,
    meet_link: initial.meet_link,
    recurrence: initial.recurrence ? [...initial.recurrence] : undefined,
    start_datetime: initial.start_datetime,
    status: 'idle',
    summary: initial.summary,
    timezone: initial.timezone,
  }
  const { data: event } = useCalendarEvent(eventId, initialCache)
  const updateWithToast = useCalendarEventUpdateToast(eventId)
  const { discard } = useCalendarEventDiscard(eventId)
  const injectChatDraft = useChatDraftStore((s) => s.injectDraft)

  const terminal = event.status === 'discarded'

  const handleReschedule = () => {
    const label = event.summary?.trim() || 'this event'
    const eventDetails = formatEventForClipboard(event)

    injectChatDraft(
      `I want to reschedule "${label}".\n\nCurrent event details:\n${eventDetails}\n\nCheck my calendar and the attendees' availability, preserve the current duration, and find a few appropriate free times. Show me the best options first, and do not reschedule the event until I choose one.`,
    )
  }

  return (
    <CalendarEvent
      actions={{
        discard: {
          disabled: terminal,
          discarding: false,
          onDiscard: discard,
        },
        onDiscardAll: discard,
        onReschedule: handleReschedule,
        status: event.status,
        update: updateWithToast,
      }}
      attendees={event.attendees}
      calendar_id={event.calendar_id}
      create_meeting_room={event.create_meeting_room}
      description={event.description}
      end_datetime={event.end_datetime}
      event_id={event.eventId}
      location={event.location}
      meet_link={event.meet_link}
      recurrence={event.recurrence}
      start_datetime={event.start_datetime}
      summary={event.summary}
      timezone={event.timezone}
    />
  )
}
