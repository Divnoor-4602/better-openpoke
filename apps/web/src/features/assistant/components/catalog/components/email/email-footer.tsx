import { ArrowSquareOutIcon } from '@phosphor-icons/react'

import type { DraftCacheValue } from '@/lib/poke/gmail'

import { Button } from '@general-poke/ui/components/button'

import type { DraftEmailSendButtonProps } from './email-send-button'

import { DraftEmailCopyButton } from './copy-button'
import { DraftEmailSendButton } from './email-send-button'

type DraftEmailFooterProps = {
  body: string
  draftId?: string
  send?: DraftEmailSendButtonProps
  status?: DraftCacheValue['status']
  subject: string
}

export const DraftEmailFooter = ({
  body,
  draftId,
  send,
  status,
  subject,
}: DraftEmailFooterProps) => {
  const isDiscarded = status === 'discarded'
  const gmailDraftUrl =
    draftId && !isDiscarded ? getGmailDraftUrl(draftId) : undefined

  return (
    <div className="mt-4 flex items-center justify-end gap-2 px-4 pt-4">
      {!isDiscarded && <DraftEmailCopyButton body={body} subject={subject} />}
      {gmailDraftUrl && (
        <Button
          aria-label="Open draft in Gmail"
          nativeButton={false}
          render={
            <a
              href={gmailDraftUrl}
              rel="noreferrer"
              target="_blank"
              title="Open draft in Gmail"
            />
          }
          size="icon-sm"
          variant="outline"
        >
          <ArrowSquareOutIcon />
        </Button>
      )}
      <DraftEmailSendButton {...(send ?? {})} status={status} />
    </div>
  )
}

const getGmailDraftUrl = (draftId: string) => {
  return `https://mail.google.com/mail/u/0/#drafts?compose=${encodeURIComponent(draftId)}`
}
