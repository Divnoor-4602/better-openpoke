import { isSameDay, isToday, isTomorrow, isYesterday } from 'date-fns'
import { formatInTimeZone, toZonedTime } from 'date-fns-tz'

const browserTimezone = (): string =>
  Intl.DateTimeFormat().resolvedOptions().timeZone

const resolveTz = (tz?: null | string): string =>
  tz && tz.trim() ? tz : browserTimezone()

// "Today" / "Tomorrow" / "Yesterday" / "Thu, May 21"
export const formatEventDay = (iso: string, tz?: null | string): string => {
  const date = new Date(iso)
  const zone = resolveTz(tz)

  const zoned = toZonedTime(date, zone)
  if (isToday(zoned)) return 'Today'
  if (isTomorrow(zoned)) return 'Tomorrow'
  if (isYesterday(zoned)) return 'Yesterday'
  return formatInTimeZone(date, zone, 'EEE, MMM d')
}

export const formatEventTimeRange = (
  startIso: string,
  endIso: string,
  tz?: null | string,
): string => {
  const start = new Date(startIso)
  const end = new Date(endIso)
  const zone = resolveTz(tz)
  const startZoned = toZonedTime(start, zone)
  const endZoned = toZonedTime(end, zone)
  if (isSameDay(startZoned, endZoned)) {
    return `${formatInTimeZone(start, zone, 'h:mm a')} – ${formatInTimeZone(end, zone, 'h:mm a')}`
  }
  return `${formatInTimeZone(start, zone, 'EEE, MMM d, h:mm a')} – ${formatInTimeZone(end, zone, 'EEE, MMM d, h:mm a')}`
}

export const isDaytime = (iso: string, tz?: null | string): boolean => {
  const zone = resolveTz(tz)
  const zoned = toZonedTime(new Date(iso), zone)
  const hour = zoned.getHours()
  return hour >= 6 && hour < 18
}

export const formatEventForClipboard = (event: {
  attendees?: null | readonly string[]
  description?: null | string
  end_datetime?: null | string
  location?: null | string
  recurrence?: null | readonly string[]
  start_datetime?: null | string
  summary?: null | string
  timezone?: null | string
}): string => {
  const sections: string[] = []
  if (event.summary) sections.push(event.summary.trim())

  const whenParts: string[] = []
  if (event.start_datetime) {
    whenParts.push(formatEventDay(event.start_datetime, event.timezone))
    if (event.end_datetime) {
      whenParts.push(
        formatEventTimeRange(
          event.start_datetime,
          event.end_datetime,
          event.timezone,
        ),
      )
    }
    const tz = formatTimezoneShort(event.timezone)
    if (tz) whenParts.push(`(${tz})`)
  }
  if (whenParts.length > 0) sections.push(`When: ${whenParts.join(' · ')}`)

  if (event.location) sections.push(`Where: ${event.location.trim()}`)
  if (event.attendees && event.attendees.length > 0) {
    sections.push(`Guests:\n${event.attendees.join('\n')}`)
  }
  if (event.description) sections.push(`Notes:\n${event.description.trim()}`)
  return sections.join('\n\n')
}

export const formatTimezoneShort = (tz?: null | string): string => {
  const zone = resolveTz(tz)
  try {
    const part = new Intl.DateTimeFormat('en-US', {
      timeZone: zone,
      timeZoneName: 'short',
    })
      .formatToParts(new Date())
      .find((p) => p.type === 'timeZoneName')
    if (part?.value) return part.value
  } catch {
    // fall through
  }
  return zone.split('/').pop() ?? zone
}
