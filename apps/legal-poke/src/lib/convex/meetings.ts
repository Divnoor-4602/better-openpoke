import { api } from '@general-poke/db/api'

import { usePokeAction } from '@/hooks/convex/use-action'
import { usePokeQuery } from '@/hooks/convex/use-query'

export const useMyMeetingsQuery = () => {
  return usePokeQuery(api.public.meeting.queries.listMyMeetings, {})
}

export const useMeetingByIdQuery = (args: { meetingId: string }) => {
  return usePokeQuery(
    api.public.meeting.queries.getById,
    args as { meetingId: never },
  )
}

export const useTranscriptTurnsQuery = (args: { meetingId: string }) => {
  return usePokeQuery(
    api.public.meeting.queries.listTranscriptTurns,
    args as { meetingId: never },
  )
}

export const useStartAdHocMeetingAction = () => {
  return usePokeAction(api.public.meeting.actions.startAdHocMeeting)
}

export const useDeleteMeetingAction = () => {
  return usePokeAction(api.public.meeting.actions.deleteMeeting)
}
