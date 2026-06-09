import { Button } from '@general-poke/ui/components/button'
import { TrashIcon } from '@phosphor-icons/react'

export type DraftEmailDiscardButtonProps = {
  disabled?: boolean
  discarding?: boolean
  onDiscard?: () => void
}

export const DraftEmailDiscardButton = ({
  disabled,
  discarding,
  onDiscard,
}: DraftEmailDiscardButtonProps) => {
  return (
    <Button
      aria-label="Discard draft"
      disabled={disabled || discarding || !onDiscard}
      onClick={onDiscard}
      size="icon-sm"
      title="Discard draft"
      variant="ghost"
    >
      <TrashIcon />
    </Button>
  )
}
