import { useParams } from '@tanstack/react-router'

import type { TooltipTrigger } from '@/components/ui/tooltip'

import { useThreads } from '@/lib/poke/thread'

import { RecentThreadsMenu } from '../components/recent-threads-menu'
import { groupThreadsByRecency } from '../lib/group-threads-by-recency'

type ThreadMenuWidgetProps = {
  handle?: TooltipHandle
}

type TooltipHandle = React.ComponentProps<typeof TooltipTrigger>['handle']

export function ThreadMenuWidget({ handle }: ThreadMenuWidgetProps) {
  const params = useParams({ strict: false })
  const activeId = params.threadId ?? null

  const { data } = useThreads()
  const threads = data?.items ?? []
  const groups = groupThreadsByRecency(threads)

  return (
    <RecentThreadsMenu activeId={activeId} groups={groups} handle={handle} />
  )
}
