import { cn } from '@general-poke/ui'
import { zThreadUpdateRequest } from '@openpoke/sdk/zod'
import { useState } from 'react'

type ThreadTitleProps = {
  className?: string
  isPending?: boolean
  onRename: (title: string) => void
  title: string
}

const shellClassName =
  'inline-flex h-7.5 w-fit max-w-88 items-center rounded-poke border bg-white px-3 font-sans text-13'

export function ThreadTitle({
  className,
  isPending = false,
  onRename,
  title,
}: ThreadTitleProps) {
  const [editing, setEditing] = useState<boolean>(false)
  const [draft, setDraft] = useState<string>(title)

  const stopEditing = () => setEditing(false)

  const commit = () => {
    const parsed = zThreadUpdateRequest.safeParse({ title: draft.trim() })
    stopEditing()
    if (!parsed.success) return
    if (parsed.data.title !== title) onRename(parsed.data.title)
  }

  if (editing) {
    return (
      <form
        className={cn(shellClassName, 'inline-grid grid-cols-1', className)}
        onSubmit={(event) => {
          event.preventDefault()
          commit()
        }}
      >
        <span
          aria-hidden="true"
          className="invisible col-start-1 row-start-1 truncate whitespace-pre"
        >
          {draft || title}
        </span>
        <input
          aria-label="Thread title"
          autoFocus
          className="col-start-1 row-start-1 w-full min-w-0 truncate border-0 bg-transparent p-0 font-sans text-13 leading-none outline-none focus:outline-none focus-visible:outline-none"
          onBlur={commit}
          onChange={(event) => setDraft(event.target.value)}
          onFocus={(event) => event.currentTarget.select()}
          onKeyDown={(event) => {
            if (event.key === 'Escape') {
              event.preventDefault()
              setDraft(title)
              stopEditing()
            }
          }}
          size={1}
          value={draft}
        />
      </form>
    )
  }

  return (
    <button
      className={cn(
        shellClassName,
        'cursor-text truncate text-left hover:bg-muted/50 disabled:cursor-default disabled:hover:bg-white bg-white',
        className,
      )}
      disabled={isPending}
      onClick={() => {
        setDraft(title)
        setEditing(true)
      }}
      type="button"
    >
      {title}
    </button>
  )
}
