import type { KeyboardEvent } from 'react'

import { PlusIcon, UserIcon, XIcon } from '@phosphor-icons/react'
import { useState } from 'react'

import { Button } from '@/components/ui/button'

const PARTICIPANT_CONTROL_CLASS =
  'flex h-5 items-center gap-1 rounded-poke border px-2 text-xs font-light'

type DraftEmailParticipantsProps = {
  bcc: EmailList
  cc: EmailList
  fromEmail?: null | string
  onAddBcc: (email: string) => void
  onAddCc: (email: string) => void
  onAddTo: (email: string) => void
  onRemoveBcc: (index: number) => void
  onRemoveCc: (index: number) => void
  onRemoveTo: (index: number) => void
  to: EmailList
}

type EmailList = string[]

export const DraftEmailParticipants = ({
  bcc,
  cc,
  fromEmail,
  onAddBcc,
  onAddCc,
  onAddTo,
  onRemoveBcc,
  onRemoveCc,
  onRemoveTo,
  to,
}: DraftEmailParticipantsProps) => {
  const [showOptionalRecipients, setShowOptionalRecipients] = useState(false)

  const fromEmails = fromEmail ? [fromEmail] : []
  const showCc = showOptionalRecipients || cc.length > 0
  const showBcc = showOptionalRecipients || bcc.length > 0
  const showOptionalRecipientTrigger =
    !showOptionalRecipients && cc.length === 0 && bcc.length === 0

  return (
    <div className="flex flex-col gap-3 border-b border-border px-4 pb-4 shadow-none">
      {fromEmails.length > 0 && (
        <ParticipantRow emails={fromEmails} label="From" />
      )}
      <ParticipantRow
        emails={to}
        label="To"
        onAdd={onAddTo}
        onRemove={onRemoveTo}
        removable
      />
      {showOptionalRecipientTrigger && (
        <Button
          className="h-5 w-fit px-1 text-xs font-normal text-muted-foreground hover:text-foreground"
          onClick={() => setShowOptionalRecipients(true)}
          size="sm"
          type="button"
          variant="outline"
        >
          Add Bcc / Cc
        </Button>
      )}
      {showCc && (
        <ParticipantRow
          emails={cc}
          label="Cc"
          onAdd={onAddCc}
          onRemove={onRemoveCc}
          removable
        />
      )}
      {showBcc && (
        <ParticipantRow
          emails={bcc}
          label="Bcc"
          onAdd={onAddBcc}
          onRemove={onRemoveBcc}
          removable
        />
      )}
    </div>
  )
}

const ParticipantRow = ({
  emails,
  label,
  onAdd,
  onRemove,
  removable = false,
}: {
  emails: EmailList
  label: string
  onAdd?: (email: string) => void
  onRemove?: (index: number) => void
  removable?: boolean
}) => {
  const [draftEmail, setDraftEmail] = useState('')
  const [isAdding, setIsAdding] = useState(false)
  const canAdd = Boolean(onAdd)

  const commitDraftEmail = () => {
    const nextEmail = draftEmail.trim()
    if (!nextEmail || !onAdd) {
      setDraftEmail('')
      setIsAdding(false)
      return
    }

    onAdd(nextEmail)
    setDraftEmail('')
    setIsAdding(false)
  }

  const handleAddKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Enter') {
      event.preventDefault()
      commitDraftEmail()
      return
    }

    if (event.key === 'Escape') {
      setDraftEmail('')
      setIsAdding(false)
    }
  }

  return (
    <div className="group/participant-row grid grid-cols-[2rem_minmax(0,1fr)] items-start gap-3">
      <span className="pt-0.5 text-xs font-normal text-muted-foreground">
        {label}
      </span>
      <div className="flex min-w-0 flex-wrap gap-1.5">
        {emails.map((email, index) => (
          <ParticipantChip
            email={email}
            index={index}
            key={`${email}:${index}`}
            onRemove={onRemove}
            removable={removable}
          />
        ))}
        {canAdd &&
          (isAdding ? (
            <ParticipantInput
              onBlur={commitDraftEmail}
              onChange={setDraftEmail}
              onKeyDown={handleAddKeyDown}
              value={draftEmail}
            />
          ) : (
            <ParticipantAddButton
              label={emails.length === 0 ? 'Add recipient' : undefined}
              onClick={() => setIsAdding(true)}
            />
          ))}
      </div>
    </div>
  )
}

const ParticipantAddButton = ({
  label,
  onClick,
}: {
  label?: string
  onClick: () => void
}) => {
  return (
    <button
      aria-label={label ?? 'Add recipient'}
      className="flex size-5 cursor-pointer items-center justify-center rounded-poke bg-transparent text-muted-foreground opacity-0 transition-[background-color,color,opacity] hover:bg-muted hover:text-foreground focus:opacity-100 focus:outline-none focus:ring-0 focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-0 group-hover/participant-row:opacity-100 group-focus-within/participant-row:opacity-100"
      onClick={onClick}
      type="button"
    >
      <PlusIcon className="size-3" />
    </button>
  )
}

const ParticipantInput = ({
  onBlur,
  onChange,
  onKeyDown,
  value,
}: {
  onBlur: () => void
  onChange: (value: string) => void
  onKeyDown: (event: KeyboardEvent<HTMLInputElement>) => void
  value: string
}) => {
  return (
    <input
      aria-label="Recipient email"
      autoFocus
      className="h-5 min-w-40 rounded-poke border bg-transparent px-2 text-xs font-light outline-none ring-0 placeholder:text-muted-foreground focus:outline-none focus:ring-0 focus-visible:outline-none focus-visible:ring-0"
      onBlur={onBlur}
      onChange={(event) => onChange(event.target.value)}
      onKeyDown={onKeyDown}
      placeholder="name@example.com"
      value={value}
    />
  )
}

const ParticipantChip = ({
  email,
  index,
  onRemove,
  removable,
}: {
  email: string
  index?: number
  onRemove?: (index: number) => void
  removable?: boolean
}) => {
  if (removable && onRemove && index !== undefined) {
    return (
      <button
        aria-label={`Remove ${email}`}
        className={`${PARTICIPANT_CONTROL_CLASS} group/chip cursor-pointer transition-colors hover:bg-muted`}
        onClick={() => onRemove(index)}
        type="button"
      >
        <UserIcon className="size-3 group-hover/chip:hidden" />
        <XIcon className="hidden size-3 group-hover/chip:block" />
        <span className="break-all text-xs font-light">{email}</span>
      </button>
    )
  }

  return (
    <div className={PARTICIPANT_CONTROL_CLASS}>
      <UserIcon className="size-3" />
      <span className="break-all text-xs font-light">{email}</span>
    </div>
  )
}
