import { useState } from 'react'

import type { DraftCacheValue } from '@/lib/poke/gmail'

import { useDebouncedCallback } from '@/hooks/use-debounce-hook'

import type { SendDraftInput, SendDraftPatch } from '../../schemas'
import type { DraftEmailDiscardButtonProps } from './email-discard-button'
import type { DraftEmailSendButtonProps } from './email-send-button'

import { DraftEmailFooter } from './email-footer'
import {
  DraftEmailContent,
  DraftEmailHeader,
  DraftEmailShell,
} from './email-layout'
import { DraftEmailParticipants } from './email-participants'

export type DraftEmailActions = {
  discard?: DraftEmailDiscardButtonProps
  send?: DraftEmailSendButtonProps
  status?: DraftCacheValue['status']
  update: (patch: SendDraftPatch) => void
}

const TEXT_DEBOUNCE_MS = 800

type DraftEmailProps = SendDraftInput & {
  actions?: DraftEmailActions
  fromEmail?: null | string
}

export const DraftEmail = ({
  actions,
  bcc = [],
  body = '',
  cc = [],
  draft_id = '',
  extra_recipients = [],
  fromEmail,
  subject = '',
  to = '',
}: DraftEmailProps) => {
  const editable = Boolean(actions)
  const terminal = actions?.status === 'sent' || actions?.status === 'discarded'

  const toList = [to, ...extra_recipients].filter(Boolean)

  const debouncedUpdate = useDebouncedCallback(
    (patch: SendDraftPatch) => actions?.update(patch),
    TEXT_DEBOUNCE_MS,
  )

  const handleRecipientAdd =
    (field: 'bcc' | 'cc' | 'to', current: string[]) => (email: string) => {
      const trimmed = email.trim()
      if (!trimmed || current.includes(trimmed)) return
      actions?.update({ [field]: [...current, trimmed] })
    }

  const handleRecipientRemove =
    (field: 'bcc' | 'cc' | 'to', current: string[]) => (index: number) => {
      actions?.update({ [field]: current.filter((_, i) => i !== index) })
    }

  return (
    <DraftEmailShell>
      <DraftEmailHeader discard={actions?.discard} />
      <DraftEmailContent>
        <DraftEmailParticipants
          bcc={bcc}
          cc={cc}
          fromEmail={fromEmail}
          onAddBcc={handleRecipientAdd('bcc', bcc)}
          onAddCc={handleRecipientAdd('cc', cc)}
          onAddTo={handleRecipientAdd('to', toList)}
          onRemoveBcc={handleRecipientRemove('bcc', bcc)}
          onRemoveCc={handleRecipientRemove('cc', cc)}
          onRemoveTo={handleRecipientRemove('to', toList)}
          to={toList}
        />
        <DraftEmailSubject
          disabled={terminal}
          editable={editable}
          onChange={(value) => debouncedUpdate({ subject: value })}
          subject={subject}
        />
        <DraftEmailBody
          body={body}
          disabled={terminal}
          editable={editable}
          onChange={(value) => debouncedUpdate({ body: value })}
        />
      </DraftEmailContent>
      <DraftEmailFooter
        body={body}
        draftId={draft_id}
        send={actions?.send}
        status={actions?.status}
        subject={subject}
      />
    </DraftEmailShell>
  )
}

type EditableTextProps = {
  disabled?: boolean
  editable: boolean
  onChange: (value: string) => void
}

const DraftEmailSubject = ({
  disabled,
  editable,
  onChange,
  subject,
}: EditableTextProps & { subject: string }) => {
  // Adopt external prop changes (e.g. agent re-edits the draft) without
  // clobbering in-flight typing — derived-state-from-props pattern.
  const [value, setValue] = useState(subject)
  const [lastSubject, setLastSubject] = useState(subject)
  if (subject !== lastSubject) {
    setLastSubject(subject)
    setValue(subject)
  }

  if (!editable) {
    if (!subject) return null
    return (
      <div className="px-4">
        <span className="text-sm font-normal">{subject}</span>
      </div>
    )
  }

  return (
    <div className="px-4">
      <input
        aria-label="Email subject"
        className="w-full bg-transparent text-sm font-normal outline-none ring-0 placeholder:text-muted-foreground focus:outline-none focus:ring-0 focus-visible:outline-none focus-visible:ring-0 disabled:cursor-not-allowed disabled:opacity-60"
        disabled={disabled}
        onChange={(event) => {
          setValue(event.target.value)
          onChange(event.target.value)
        }}
        placeholder="Subject"
        value={value}
      />
    </div>
  )
}

const DraftEmailBody = ({
  body,
  disabled,
  editable,
  onChange,
}: EditableTextProps & { body: string }) => {
  const [value, setValue] = useState(body)
  const [lastBody, setLastBody] = useState(body)
  if (body !== lastBody) {
    setLastBody(body)
    setValue(body)
  }

  if (!editable) {
    if (!body) return null
    return (
      <div className="whitespace-pre-wrap px-4 text-13 font-light leading-relaxed">
        {body}
      </div>
    )
  }

  return (
    <textarea
      aria-label="Email body"
      className="w-full resize-none overflow-y-auto bg-transparent px-4 text-13 font-light leading-relaxed outline-none ring-0 scrollbar-thin [scrollbar-color:#d4d4d4_transparent] placeholder:text-muted-foreground focus:outline-none focus:ring-0 focus-visible:outline-none focus-visible:ring-0 disabled:cursor-not-allowed disabled:opacity-60"
      disabled={disabled}
      onChange={(event) => {
        setValue(event.target.value)
        onChange(event.target.value)
      }}
      placeholder="Email body"
      rows={8}
      value={value}
    />
  )
}
