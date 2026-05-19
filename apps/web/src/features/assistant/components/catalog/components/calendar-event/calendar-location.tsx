import { MapPinLineIcon } from '@phosphor-icons/react'

export const CalendarEventLocation = ({ location }: { location?: string }) => {
  if (!location) return null

  return (
    <div className="mt-5 flex items-center gap-1 text-muted-foreground">
      <MapPinLineIcon className="size-3" />
      <span className="text-xs font-light">{location}</span>
    </div>
  )
}
