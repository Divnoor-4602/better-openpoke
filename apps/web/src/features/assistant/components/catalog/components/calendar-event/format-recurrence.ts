import * as rrulePkg from 'rrule'

const { RRule } = rrulePkg

export const formatRecurrence = (
  recurrence?: null | readonly string[],
): string => {
  if (!recurrence || recurrence.length === 0) return 'One time'

  const rruleLine = recurrence.find((line) => line.startsWith('RRULE:'))
  if (!rruleLine) return 'Recurring'

  try {
    const rule = RRule.fromString(rruleLine)
    const text = rule.toText().trim()
    return text ? capitalize(text) : 'Recurring'
  } catch {
    return 'Recurring'
  }
}

const capitalize = (s: string): string => {
  if (s.length === 0) return s
  const first = s.charAt(0).toUpperCase()
  return first + s.slice(1)
}
