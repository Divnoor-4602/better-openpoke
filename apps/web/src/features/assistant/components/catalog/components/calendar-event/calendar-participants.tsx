import type { KeyboardEvent } from 'react'

import { PlusIcon, UserIcon, XIcon } from '@phosphor-icons/react'
import { useEffect, useRef, useState } from 'react'

const PARTICIPANT_CONTROL_CLASS =
  'flex h-5 items-center gap-1 rounded-poke border px-2 text-xs font-light'

type CalendarEventParticipantsProps = {
  attendees?: string[]
  disabled?: boolean
  onAdd?: (email: string) => void
  onRemove?: (index: number) => void
}

export const CalendarEventParticipants = ({
  attendees = [],
  disabled = false,
  onAdd,
  onRemove,
}: CalendarEventParticipantsProps) => {
  const editable = Boolean(onAdd)
  const removable = Boolean(onRemove) && !disabled

  if (!editable && attendees.length === 0) {
    return (
      <div className="mt-5 text-xs font-light text-muted-foreground">
        No attendees
      </div>
    )
  }

  return (
    <div className="group/participant-row mt-5 flex min-w-0 flex-wrap items-center gap-1.5">
      {attendees.length === 0 && editable && (
        <span className="text-xs font-light text-muted-foreground">
          No attendees
        </span>
      )}
      {attendees.map((email, index) => (
        <ParticipantChip
          disabled={disabled}
          email={email}
          index={index}
          key={`${email}:${index}`}
          onRemove={onRemove}
          removable={removable}
        />
      ))}
      {editable && <AddParticipant disabled={disabled} onAdd={onAdd} />}
    </div>
  )
}

const AddParticipant = ({
  disabled,
  onAdd,
}: {
  disabled: boolean
  onAdd?: (email: string) => void
}) => {
  const [isAdding, setIsAdding] = useState(false)
  const [draft, setDraft] = useState('')

  const commit = () => {
    const next = draft.trim()
    if (!next || !onAdd) {
      setDraft('')
      setIsAdding(false)
      return
    }
    onAdd(next)
    setDraft('')
    setIsAdding(false)
  }

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Enter') {
      event.preventDefault()
      commit()
      return
    }
    if (event.key === 'Escape') {
      setDraft('')
      setIsAdding(false)
    }
  }

  if (isAdding) {
    return (
      <ParticipantInput
        onBlur={commit}
        onChange={setDraft}
        onKeyDown={onKeyDown}
        value={draft}
      />
    )
  }

  return (
    <ParticipantAddButton
      disabled={disabled}
      onClick={() => setIsAdding(true)}
    />
  )
}

const ParticipantAddButton = ({
  disabled,
  onClick,
}: {
  disabled: boolean
  onClick: () => void
}) => {
  return (
    <button
      aria-label="Add attendee"
      className="flex size-5 cursor-pointer items-center justify-center rounded-poke bg-transparent text-muted-foreground opacity-0 transition-[background-color,color,opacity] hover:bg-muted hover:text-foreground focus:opacity-100 focus:outline-none focus:ring-0 focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-0 disabled:cursor-not-allowed disabled:opacity-30 group-hover/participant-row:opacity-100 group-focus-within/participant-row:opacity-100"
      disabled={disabled}
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
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  return (
    <input
      aria-label="Attendee email"
      className="h-5 min-w-40 rounded-poke border bg-transparent px-2 text-xs font-light outline-none ring-0 placeholder:text-muted-foreground focus:outline-none focus:ring-0 focus-visible:outline-none focus-visible:ring-0"
      onBlur={onBlur}
      onChange={(event) => onChange(event.target.value)}
      onKeyDown={onKeyDown}
      placeholder="name@example.com"
      ref={inputRef}
      value={value}
    />
  )
}

const ParticipantChip = ({
  disabled,
  email,
  index,
  onRemove,
  removable,
}: {
  disabled: boolean
  email: string
  index: number
  onRemove?: (index: number) => void
  removable: boolean
}) => {
  if (removable && onRemove) {
    return (
      <button
        aria-label={`Remove ${email}`}
        className={`${PARTICIPANT_CONTROL_CLASS} group/chip cursor-pointer transition-colors hover:bg-muted disabled:cursor-not-allowed disabled:opacity-50`}
        disabled={disabled}
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
