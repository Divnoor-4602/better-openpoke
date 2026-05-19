import type { DraftCacheValue } from '@/lib/poke/gmail'

import { Button } from '@/components/ui/button'

export type DraftEmailSendButtonProps = {
  disabled?: boolean
  onSend?: () => void
  sending?: boolean
  status?: DraftCacheValue['status']
}

export const DraftEmailSendButton = ({
  disabled,
  onSend,
  sending,
  status = 'idle',
}: DraftEmailSendButtonProps) => {
  if (status === 'discarded') {
    return (
      <Button disabled size="sm" variant="outline">
        Discarded
      </Button>
    )
  }

  if (status === 'sent') {
    return (
      <Button disabled size="sm">
        Sent
      </Button>
    )
  }

  return (
    <Button
      disabled={disabled || sending || !onSend}
      onClick={onSend}
      size="sm"
    >
      {sending ? 'Sending' : 'Send'}
    </Button>
  )
}
