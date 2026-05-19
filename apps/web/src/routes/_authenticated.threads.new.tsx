import { createFileRoute } from '@tanstack/react-router'

import { AppLayout, topbarTooltip } from '@/components/app-layout'
import { WorkspaceMenuWidget } from '@/features/auth/widgets/workspace-menu-widget'
import { GoogleConnectionPrompt } from '@/features/integration/components/google-connection-prompt'
import { GoogleEmptyStateFooter } from '@/features/integration/components/google-empty-state-footer'
import { GoogleTopbarMenu } from '@/features/integration/components/google-topbar-menu'
import { NewThreadWidget } from '@/features/thread/widgets/new-thread-widget'

export const Route = createFileRoute('/_authenticated/threads/new')({
  component: NewThreadRoute,
})

function NewThreadRoute() {
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
      <NewThreadWidget
        slots={{
          emptyStateFooter: <GoogleEmptyStateFooter />,
          integrationPrompt: GoogleConnectionPrompt,
        }}
      />
    </AppLayout>
  )
}
