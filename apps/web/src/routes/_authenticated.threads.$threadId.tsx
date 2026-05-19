import { createFileRoute, redirect } from '@tanstack/react-router'

import { AppLayout, topbarTooltip } from '@/components/app-layout'
import { WorkspaceMenuWidget } from '@/features/auth/widgets/workspace-menu-widget'
import { GoogleConnectionPrompt } from '@/features/integration/components/google-connection-prompt'
import { GoogleEmptyStateFooter } from '@/features/integration/components/google-empty-state-footer'
import { GoogleTopbarMenu } from '@/features/integration/components/google-topbar-menu'
import { ThreadDetailWidget } from '@/features/thread/widgets/thread-detail-widget'
import { poke } from '@/lib/poke/client'
import { threadKeys } from '@/lib/poke/thread'

export const Route = createFileRoute('/_authenticated/threads/$threadId')({
  component: ThreadDetailRoute,
  loader: async ({ context, params }) => {
    try {
      await context.queryClient.ensureQueryData({
        queryFn: async () => {
          const { data } = await poke.threads.messages.list(params.threadId)
          return data
        },
        queryKey: [...threadKeys.messages(params.threadId), undefined],
      })
    } catch {
      throw redirect({ to: '/threads/new' })
    }
  },
})

function ThreadDetailRoute() {
  const { threadId } = Route.useParams()
  return (
    <AppLayout
      unwrapped
      topbarEnd={
        <div className="flex items-center gap-1">
          <GoogleTopbarMenu handle={topbarTooltip} />
          <WorkspaceMenuWidget />
        </div>
      }
    >
      <ThreadDetailWidget
        key={threadId}
        slots={{
          emptyStateFooter: <GoogleEmptyStateFooter />,
          integrationPrompt: GoogleConnectionPrompt,
        }}
        threadId={threadId}
      />
    </AppLayout>
  )
}
