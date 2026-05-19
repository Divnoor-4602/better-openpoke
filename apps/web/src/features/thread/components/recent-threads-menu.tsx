import { ChatIcon } from '@phosphor-icons/react'
import { Link } from '@tanstack/react-router'

import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'

import type { ThreadGroup } from '../lib/group-threads-by-recency'

type RecentThreadsMenuProps = {
  activeId?: null | string
  groups: ThreadGroup[]
  handle?: TooltipHandle
}

type TooltipHandle = React.ComponentProps<typeof TooltipTrigger>['handle']

export const RecentThreadsMenu = ({
  activeId,
  groups,
  handle,
}: RecentThreadsMenuProps) => {
  const isEmpty = groups.length === 0

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <TooltipTrigger
            handle={handle}
            payload="Recents"
            render={
              <Button aria-label="Recents" size="icon-sm" variant="ghost" />
            }
          >
            <ChatIcon />
          </TooltipTrigger>
        }
      />
      <DropdownMenuContent
        align="end"
        className="flex max-h-64 w-50 flex-col gap-1 overflow-y-auto rounded-poke shadow-xs scrollbar-thin [scrollbar-color:#e5e5e5_transparent] py-2"
        sideOffset={8}
      >
        {isEmpty ? (
          <div className="px-2 py-1.5 text-xs text-muted-foreground">
            No threads yet.
          </div>
        ) : (
          groups.map((group, idx) => (
            <DropdownMenuGroup
              className="flex flex-col gap-1 mt-1"
              key={group.label ?? `tail-${idx}`}
            >
              {group.label ? (
                <DropdownMenuLabel className="px-2 py-0 text-[10px] font-medium text-muted-foreground">
                  {group.label}
                </DropdownMenuLabel>
              ) : null}
              {group.items.map((thread) => (
                <DropdownMenuItem
                  key={thread.threadId}
                  render={
                    <Link
                      className={cn(
                        thread.threadId === activeId &&
                          'bg-muted text-foreground',
                      )}
                      params={{ threadId: thread.threadId }}
                      preload="intent"
                      to="/threads/$threadId"
                    />
                  }
                >
                  <span className="truncate">
                    {thread.title ?? 'New thread'}
                  </span>
                </DropdownMenuItem>
              ))}
            </DropdownMenuGroup>
          ))
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
