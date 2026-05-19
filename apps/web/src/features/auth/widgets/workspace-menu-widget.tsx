import { SignOutIcon, UserIcon } from '@phosphor-icons/react'

import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useAuth } from '@/features/auth/hooks/use-auth'

export const WorkspaceMenuWidget = () => {
  const { logout, logoutMutation, workspaceId } = useAuth()
  if (!workspaceId) return null

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <Button
            aria-label={`Workspace ${workspaceId}`}
            size="icon-sm"
            variant="ghost"
          >
            <UserIcon />
          </Button>
        }
      />
      <DropdownMenuContent
        align="end"
        className="w-48 rounded-poke shadow-xs"
        sideOffset={10}
      >
        <DropdownMenuGroup>
          <DropdownMenuItem className="gap-1">
            <UserIcon />
            <span className="min-w-0 flex-1 truncate">{workspaceId}</span>
          </DropdownMenuItem>
        </DropdownMenuGroup>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          className="gap-1"
          disabled={logoutMutation.isPending}
          onClick={() => {
            void logout()
          }}
          variant="destructive"
        >
          <SignOutIcon />
          <span className="min-w-0 flex-1 truncate">
            {logoutMutation.isPending ? 'Signing out' : 'Sign out'}
          </span>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
