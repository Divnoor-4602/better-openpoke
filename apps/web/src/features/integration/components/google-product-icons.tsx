import GmailIcon from '@/assets/gmail-icon'
import GoogleCalendarIcon from '@/assets/google-calendar-icon'
import GoogleMeetIcon from '@/assets/google-meet-icon'
import { cn } from '@/lib/utils'

type GoogleProductIconsProps = {
  className?: string
  connected?: boolean
}

export const GoogleProductIcons = ({
  className,
  connected,
}: GoogleProductIconsProps) => {
  return (
    <div
      className={cn(
        'flex items-center gap-2 transition-opacity',
        connected ? 'opacity-100' : 'opacity-70',
        className,
      )}
    >
      <GmailIcon className="h-3 w-auto" />
      <GoogleMeetIcon className="h-3 w-auto" />
      <GoogleCalendarIcon className="h-3 w-auto" />
    </div>
  )
}
