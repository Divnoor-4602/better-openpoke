import { createFileRoute } from '@tanstack/react-router'

import { MeetingDetail } from '@/features/meetings/components/meeting-detail'

export const Route = createFileRoute('/_protected/meetings/$meetingId')({
  component: MeetingDetailRoute,
})

function MeetingDetailRoute() {
  const { meetingId } = Route.useParams()
  return <MeetingDetail meetingId={meetingId} />
}
