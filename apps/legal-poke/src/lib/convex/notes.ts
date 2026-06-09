import { api } from '@general-poke/db/api'

import { usePokeAction } from '@/hooks/convex/use-action'
import { usePokeMutation } from '@/hooks/convex/use-mutation'
import { usePokeQuery } from '@/hooks/convex/use-query'

export const useMyNotesQuery = () => {
  return usePokeQuery(api.public.meeting_notes.queries.listForUser, {})
}

export const useNoteByIdQuery = (args: { noteId: string }) => {
  return usePokeQuery(
    api.public.meeting_notes.queries.getById,
    args as { noteId: never },
  )
}

export const useNoteForMeetingQuery = (args: { meetingId: string }) => {
  return usePokeQuery(
    api.public.meeting_notes.queries.getForMeeting,
    args as { meetingId: never },
  )
}

export const useUpdateNoteMutation = () => {
  return usePokeMutation(api.public.meeting_notes.mutations.updateNote)
}

export const useRegenerateNoteAction = () => {
  return usePokeAction(api.public.meeting_notes.mutations.regenerateForMeeting)
}

export const useDeleteNoteMutation = () => {
  return usePokeMutation(api.public.meeting_notes.mutations.deleteNote)
}
