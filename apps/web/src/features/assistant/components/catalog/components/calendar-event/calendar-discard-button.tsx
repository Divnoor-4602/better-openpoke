import { TrashIcon } from '@phosphor-icons/react'

import { Button } from '@/components/ui/button'

export type CalendarEventDiscardButtonProps = {
  disabled?: boolean
  discarding?: boolean
  onDiscard?: () => void
}

export const CalendarEventDiscardButton = ({
  disabled,
  discarding,
  onDiscard,
}: CalendarEventDiscardButtonProps) => {
  return (
    <Button
      aria-label="Discard event"
      disabled={disabled || discarding || !onDiscard}
      onClick={onDiscard}
      size="icon-sm"
      title="Discard event"
      variant="ghost"
    >
      <TrashIcon />
    </Button>
  )
}
