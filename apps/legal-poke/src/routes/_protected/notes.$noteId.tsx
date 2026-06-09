import { createFileRoute } from '@tanstack/react-router'

import { NoteDetail } from '@/features/notes/components/note-detail'

export const Route = createFileRoute('/_protected/notes/$noteId')({
  component: NoteDetailRoute,
})

function NoteDetailRoute() {
  const { noteId } = Route.useParams()
  return <NoteDetail noteId={noteId} />
}
