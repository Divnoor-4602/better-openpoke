import type { TMeetingNotes } from '@general-poke/db/types'

import { useUser } from '@clerk/tanstack-react-start'
import { AI_DISCLAIMER_TEXT } from '@general-poke/db/compliance'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@general-poke/ui/components/alert-dialog'
import { Link, useNavigate } from '@tanstack/react-router'
import {
  AlertTriangle,
  ArrowLeft,
  CalendarDays,
  FolderPlus,
  RefreshCw,
  Trash2,
  User as UserIcon,
} from 'lucide-react'
import { useState } from 'react'
import ReactMarkdown from 'react-markdown'

import { useDebouncedCallback } from '@/hooks/use-debounced-callback'
import {
  useDeleteNoteMutation,
  useNoteByIdQuery,
  useRegenerateNoteAction,
  useUpdateNoteMutation,
} from '@/lib/convex/notes'

const SAVE_DEBOUNCE_MS = 800

const formatDayChip = (ts: number) => {
  const d = new Date(ts)
  const today = new Date()
  const sameDay =
    d.getFullYear() === today.getFullYear() &&
    d.getMonth() === today.getMonth() &&
    d.getDate() === today.getDate()
  if (sameDay) return 'Today'
  return d.toLocaleDateString(undefined, { day: 'numeric', month: 'short' })
}

type Props = { noteId: string }

export const NoteDetail = ({ noteId }: Props) => {
  const noteQuery = useNoteByIdQuery({ noteId })
  const updateNote = useUpdateNoteMutation()
  const regenerate = useRegenerateNoteAction()
  const deleteNote = useDeleteNoteMutation()
  const navigate = useNavigate()
  const [confirmDelete, setConfirmDelete] = useState(false)

  if (noteQuery.isPending) return <NoteDetailSkeleton />
  if (!noteQuery.data) return <NoteNotFound />

  const note = noteQuery.data

  return (
    <>
      <NoteDetailLoaded
        deleting={deleteNote.isPending}
        note={note}
        onDelete={() => setConfirmDelete(true)}
        onRegenerate={(meetingId) => regenerate.mutateAsync({ meetingId })}
        onUpdate={(patch) =>
          updateNote.mutateAsync({ noteId: note._id, ...patch })
        }
        regenerating={regenerate.isPending}
      />
      <AlertDialog
        onOpenChange={(open) => {
          if (!open) setConfirmDelete(false)
        }}
        open={confirmDelete}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete note</AlertDialogTitle>
            <AlertDialogDescription>
              This permanently deletes this note. The underlying meeting and
              transcript are preserved. You can regenerate notes later if you
              want them back.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={async () => {
                await deleteNote.mutateAsync({ noteId: note._id })
                setConfirmDelete(false)
                await navigate({ to: '/' })
              }}
              variant="destructive"
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}

type LoadedProps = {
  deleting: boolean
  note: TMeetingNotes
  onDelete: () => void
  onRegenerate: (meetingId: string) => Promise<unknown>
  onUpdate: (patch: { content?: string; title?: string }) => Promise<unknown>
  regenerating: boolean
}

const NoteDetailLoaded = ({
  deleting,
  note,
  onDelete,
  onRegenerate,
  onUpdate,
  regenerating,
}: LoadedProps) => {
  const { user } = useUser()
  const userLabel =
    user?.firstName ?? user?.emailAddresses[0]?.emailAddress ?? 'Me'

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-6 py-10">
      <div className="flex items-center justify-between">
        <Link
          className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-900"
          to="/"
        >
          <ArrowLeft className="size-4" />
          Back
        </Link>
        <div className="flex items-center gap-2">
          <button
            className="flex items-center gap-1.5 rounded-md border border-gray-200 bg-white px-3 py-1.5 text-sm text-red-600 hover:bg-red-50 disabled:opacity-50"
            disabled={deleting}
            onClick={onDelete}
            type="button"
          >
            <Trash2 className="size-4" />
            {deleting ? 'Deleting…' : 'Delete'}
          </button>
          <button
            className="flex items-center gap-2 rounded-md border border-gray-200 bg-white px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50"
            disabled={regenerating}
            onClick={() => onRegenerate(note.meetingId)}
            type="button"
          >
            <RefreshCw
              className={`size-4 ${regenerating ? 'animate-spin' : ''}`}
            />
            {regenerating ? 'Regenerating…' : 'Regenerate summary'}
          </button>
        </div>
      </div>

      <NoteTitleField
        initial={note.title}
        onSave={(title) => onUpdate({ title })}
      />

      <ChipRow
        dayLabel={formatDayChip(note.generatedAt)}
        userLabel={userLabel}
      />

      <div className="flex items-start gap-2 rounded border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
        <AlertTriangle className="mt-0.5 size-4 shrink-0" />
        <span>{AI_DISCLAIMER_TEXT}</span>
      </div>

      <NoteBodyField
        initial={note.content}
        onSave={(content) => onUpdate({ content })}
      />
    </div>
  )
}

const ChipRow = ({
  dayLabel,
  userLabel,
}: {
  dayLabel: string
  userLabel: string
}) => (
  <div className="flex flex-wrap items-center gap-2">
    <Chip icon={<CalendarDays className="size-3.5" />}>{dayLabel}</Chip>
    <Chip icon={<UserIcon className="size-3.5" />}>{userLabel}</Chip>
    <Chip icon={<FolderPlus className="size-3.5" />} muted>
      Add to folder
    </Chip>
  </div>
)

const Chip = ({
  children,
  icon,
  muted,
}: {
  children: React.ReactNode
  icon: React.ReactNode
  muted?: boolean
}) => (
  <span
    className={`flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs ${
      muted ? 'border-gray-200 text-gray-500' : 'border-gray-300 text-gray-700'
    }`}
  >
    {icon}
    {children}
  </span>
)

const NoteTitleField = ({
  initial,
  onSave,
}: {
  initial: string
  onSave: (value: string) => Promise<unknown>
}) => {
  const [value, setValue] = useState(initial)
  const debouncedSave = useDebouncedCallback(
    (next: string) => void onSave(next),
    SAVE_DEBOUNCE_MS,
  )
  return (
    <input
      aria-label="Note title"
      className="font-serif text-4xl font-medium text-gray-900 outline-none ring-0 placeholder:text-gray-400 focus:outline-none focus:ring-0"
      key={initial}
      onChange={(e) => {
        setValue(e.target.value)
        debouncedSave(e.target.value)
      }}
      placeholder="Untitled"
      value={value}
    />
  )
}

const NoteBodyField = ({
  initial,
  onSave,
}: {
  initial: string
  onSave: (value: string) => Promise<unknown>
}) => {
  const [editing, setEditing] = useState(false)
  const [value, setValue] = useState(initial)
  const debouncedSave = useDebouncedCallback(
    (next: string) => void onSave(next),
    SAVE_DEBOUNCE_MS,
  )

  if (editing) {
    return (
      <textarea
        aria-label="Note body"
        autoFocus
        className="min-h-[60vh] w-full resize-none bg-transparent font-mono text-sm leading-relaxed text-gray-800 outline-none ring-0 focus:outline-none focus:ring-0"
        onBlur={() => setEditing(false)}
        onChange={(e) => {
          setValue(e.target.value)
          debouncedSave(e.target.value)
        }}
        placeholder="Write notes…"
        value={value}
      />
    )
  }

  return (
    <button
      aria-label="Edit note body"
      className="min-h-[60vh] cursor-text text-left text-gray-800"
      onClick={() => setEditing(true)}
      type="button"
    >
      {value ? (
        <div className="prose prose-sm max-w-none [&_h1]:before:content-['#_'] [&_h1]:before:text-gray-400 [&_h1]:before:font-normal [&_h1]:text-xl [&_h1]:font-semibold [&_h1]:mt-6 [&_h1]:mb-2 [&_li]:my-1 [&_p]:my-2 [&_ul]:list-disc [&_ul]:pl-5">
          <ReactMarkdown>{value}</ReactMarkdown>
        </div>
      ) : (
        <span className="text-gray-400">Write notes</span>
      )}
    </button>
  )
}

const NoteDetailSkeleton = () => (
  <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-6 py-10">
    <div className="flex items-center justify-between">
      <div className="h-5 w-16 animate-pulse rounded bg-gray-200" />
      <div className="h-8 w-44 animate-pulse rounded bg-gray-200" />
    </div>
    <div className="h-10 w-2/3 animate-pulse rounded bg-gray-200" />
    <div className="flex gap-2">
      <div className="h-6 w-20 animate-pulse rounded bg-gray-200" />
      <div className="h-6 w-16 animate-pulse rounded bg-gray-200" />
      <div className="h-6 w-32 animate-pulse rounded bg-gray-200" />
    </div>
    <div className="flex flex-col gap-3">
      <div className="h-5 w-1/3 animate-pulse rounded bg-gray-200" />
      <div className="h-4 w-3/4 animate-pulse rounded bg-gray-100" />
      <div className="h-4 w-2/3 animate-pulse rounded bg-gray-100" />
      <div className="h-4 w-3/5 animate-pulse rounded bg-gray-100" />
      <div className="mt-4 h-5 w-1/4 animate-pulse rounded bg-gray-200" />
      <div className="h-4 w-3/4 animate-pulse rounded bg-gray-100" />
      <div className="h-4 w-3/5 animate-pulse rounded bg-gray-100" />
    </div>
  </div>
)

const NoteNotFound = () => (
  <div className="mx-auto flex w-full max-w-3xl flex-col items-center gap-3 px-6 py-20 text-center">
    <h1 className="text-2xl font-medium">Note not found</h1>
    <p className="text-sm text-gray-500">
      It may have been deleted or you don&apos;t have access.
    </p>
    <Link className="text-sm text-blue-600 hover:underline" to="/">
      Back to home
    </Link>
  </div>
)
