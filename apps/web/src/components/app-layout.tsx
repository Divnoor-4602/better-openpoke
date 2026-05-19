import { DEFAULT_OPENPOKE_BASE_URL } from '@openpoke/sdk'
import { ArrowCounterClockwiseIcon, ClockIcon } from '@phosphor-icons/react'

import { Layout, LayoutContent } from '@/components/shared/layout'
import {
  Topbar,
  TopbarLeft,
  TopbarMenu,
  TopbarMenuGroup,
  TopbarRight,
} from '@/components/shared/topbar'
import { Button } from '@/components/ui/button'
import {
  Tooltip,
  TooltipContent,
  TooltipCreateHandle,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { NewThreadButton } from '@/features/thread/components/new-thread-button'
import { ThreadMenuWidget } from '@/features/thread/widgets/thread-menu-widget'
import { ThreadTitleWidget } from '@/features/thread/widgets/thread-title-widget'

type AppLayoutProps = {
  children: React.ReactNode
  topbarEnd?: React.ReactNode
  unwrapped?: boolean
}

export const topbarTooltip = TooltipCreateHandle<React.ReactNode>()

export const AppLayout = ({
  children,
  topbarEnd,
  unwrapped,
}: AppLayoutProps) => {
  return (
    <Layout>
      <LayoutContent unwrapped={unwrapped}>{children}</LayoutContent>
      <Topbar>
        <TopbarLeft>
          <ThreadTitleWidget />
        </TopbarLeft>
        <TopbarRight>
          <TopbarMenu>
            <NewThreadButton handle={topbarTooltip} />
            <TopbarMenuGroup>
              <ThreadMenuWidget handle={topbarTooltip} />
              <TooltipTrigger
                handle={topbarTooltip}
                payload="Reminders"
                render={
                  <Button
                    aria-label="Reminders"
                    size="icon-sm"
                    variant="ghost"
                  />
                }
              >
                <ClockIcon />
              </TooltipTrigger>
              {import.meta.env.DEV ? (
                <Button
                  aria-label="Reset dev state"
                  onClick={handleReset}
                  size="icon-sm"
                  title="Reset dev state"
                  variant="ghost"
                >
                  <ArrowCounterClockwiseIcon />
                </Button>
              ) : null}
            </TopbarMenuGroup>
            {topbarEnd ? <TopbarMenuGroup>{topbarEnd}</TopbarMenuGroup> : null}
            <TopbarTooltip />
          </TopbarMenu>
        </TopbarRight>
      </Topbar>
    </Layout>
  )
}

const TopbarTooltip = () => {
  return (
    <Tooltip handle={topbarTooltip}>
      {({ payload }) => (
        <TooltipContent side="bottom" sideOffset={8}>
          {payload}
        </TooltipContent>
      )}
    </Tooltip>
  )
}

const handleReset = async () => {
  if (
    !window.confirm(
      'Wipe all threads, agent runs, memory, and conversation logs?',
    )
  )
    return
  const res = await fetch(`${DEFAULT_OPENPOKE_BASE_URL}/api/dev/reset`, {
    method: 'POST',
  })
  if (!res.ok) {
    window.alert(`Reset failed: ${res.status}`)
    return
  }
  window.location.reload()
}
