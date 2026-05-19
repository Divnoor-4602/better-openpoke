import type { DraftCacheValue } from '@/lib/poke/gmail'

import {
  useDiscardDraft,
  useDraft,
  useSendDraft,
  useUpdateDraft,
} from '@/lib/poke/gmail'
import { useGoogleIntegrationStatus } from '@/lib/poke/integrations'

import type { SendDraftInput, SendDraftPatch } from '../schemas'

import { DraftEmail } from '../components/email'

export const DraftEmailWidget = (props: SendDraftInput) => {
  const statusQuery = useGoogleIntegrationStatus()
  const fromEmail = statusQuery.data?.email ?? null

  if (!props.draft_id) {
    return <DraftEmail {...props} fromEmail={fromEmail} />
  }
  return (
    <DraftEmailWidgetActive
      draftId={props.draft_id}
      fromEmail={fromEmail}
      initial={props}
    />
  )
}

const DraftEmailWidgetActive = ({
  draftId,
  fromEmail,
  initial,
}: {
  draftId: string
  fromEmail: null | string
  initial: SendDraftInput
}) => {
  const initialCache: DraftCacheValue = {
    bcc: initial.bcc,
    body: initial.body,
    cc: initial.cc,
    draftId,
    status: 'idle',
    subject: initial.subject,
    to: initial.to,
  }
  const { data: draft } = useDraft(draftId, initialCache)
  const sendMutation = useSendDraft(draftId)
  const updateMutation = useUpdateDraft(draftId)
  const discardMutation = useDiscardDraft(draftId)

  const terminal = draft.status === 'sent' || draft.status === 'discarded'

  const update = (patch: SendDraftPatch) => {
    updateMutation.mutate(patch)
  }

  return (
    <DraftEmail
      actions={{
        discard: {
          disabled: terminal,
          discarding: discardMutation.isPending,
          onDiscard: () => discardMutation.mutate(),
        },
        send: {
          disabled: terminal,
          onSend: () => sendMutation.mutate(),
          sending: sendMutation.isPending,
        },
        status: draft.status,
        update,
      }}
      bcc={draft.bcc}
      body={draft.body}
      cc={draft.cc}
      draft_id={draft.draftId}
      fromEmail={fromEmail}
      subject={draft.subject}
      to={draft.to}
    />
  )
}
