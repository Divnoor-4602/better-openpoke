import type { ReactNode } from 'react'

import GoogleCalendarIcon from '@/assets/google-calendar-icon'

import type { CalendarEventDiscardButtonProps } from './calendar-discard-button'

import { CalendarEventDiscardButton } from './calendar-discard-button'

export const CalendarEventShell = ({ children }: { children: ReactNode }) => {
  return (
    <div className="mt-4 w-full max-w-lg rounded-poke border bg-white py-4">
      {children}
    </div>
  )
}

type CalendarEventHeaderProps = {
  discard?: CalendarEventDiscardButtonProps
}

export const CalendarEventHeader = ({ discard }: CalendarEventHeaderProps) => {
  return (
    <div className="flex items-center justify-between border-b border-border px-4 pb-3 shadow-none">
      <div className="flex items-center gap-2">
        <GoogleCalendarIcon className="size-3.5" />
        <span className="text-13 font-normal">Create Event</span>
      </div>
      <CalendarEventDiscardButton {...(discard ?? {})} />
    </div>
  )
}

export const CalendarEventContent = ({ children }: { children: ReactNode }) => {
  return <div className="px-4 pt-4">{children}</div>
}
