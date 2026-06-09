import type { ComponentProps } from 'react'

import { cn } from '@general-poke/ui'
import { Button } from '@general-poke/ui/components/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@general-poke/ui/components/dropdown-menu'
import { TooltipTrigger } from '@general-poke/ui/components/tooltip'
import { SignOutIcon, UserIcon } from '@phosphor-icons/react'

import GoogleIcon from '@/assets/google-icon'

import {
  getGoogleIntegrationLabel,
  useGoogleIntegration,
} from '../hooks/use-google-integration'

type GoogleTopbarMenuProps = {
  handle?: TooltipHandle
}

type TooltipHandle = ComponentProps<typeof TooltipTrigger>['handle']

export const GoogleTopbarMenu = ({ handle }: GoogleTopbarMenuProps) => {
  const {
    connect,
    connected,
    disconnect,
    email,
    isConnecting,
    isDisconnecting,
    status,
  } = useGoogleIntegration()
  const label = getGoogleIntegrationLabel(status)
  const title = connected
    ? email
      ? `Google connected as ${email}`
      : 'Google connected'
    : label

  if (!connected)
    return (
      <TooltipTrigger
        handle={handle}
        payload="Connect to Google"
        render={<GoogleTopbarMenuTrigger connect={connect} title={title} />}
      />
    )

  const trigger = (
    <GoogleTopbarMenuTrigger
      connect={connect}
      connected={connected}
      isConnecting={isConnecting}
      isDisconnecting={isDisconnecting}
      title={title}
    />
  )

  return (
    <DropdownMenu>
      <DropdownMenuTrigger render={trigger} />
      <DropdownMenuContent
        align="end"
        className="w-40 rounded-poke shadow-xs"
        sideOffset={10}
      >
        <DropdownMenuGroup>
          <DropdownMenuItem className="gap-1">
            <UserIcon />
            <span className="min-w-0 flex-1 truncate">
              {email ?? 'Google connected'}
            </span>
          </DropdownMenuItem>
        </DropdownMenuGroup>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          className="gap-1"
          disabled={isDisconnecting}
          onClick={disconnect}
          variant="destructive"
        >
          <SignOutIcon />
          <span className="min-w-0 flex-1 truncate">
            {isDisconnecting ? 'Disconnecting' : 'Disconnect'}
          </span>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

type GoogleTopbarMenuTriggerProps = Omit<
  ComponentProps<typeof Button>,
  'children' | 'onClick' | 'size' | 'title' | 'variant'
> & {
  connect: () => void
  connected?: boolean
  isConnecting?: boolean
  isDisconnecting?: boolean
  onClick?: ComponentProps<typeof Button>['onClick']
  title: string
}

export const GoogleTopbarMenuTrigger = ({
  connect,
  connected,
  isConnecting,
  isDisconnecting,
  onClick,
  title,
  ...props
}: GoogleTopbarMenuTriggerProps) => {
  return (
    <Button
      {...props}
      aria-label={title}
      disabled={isConnecting || isDisconnecting}
      onClick={connected ? onClick : connect}
      size="icon-sm"
      title={title}
      variant="ghost"
    >
      <GoogleIcon className="size-3" />
      <span
        className={cn(
          'absolute right-1 top-1 size-1.5 rounded-full ring-1 ring-white',
          connected
            ? 'bg-green-200'
            : isConnecting
              ? 'bg-amber-500'
              : 'bg-muted-foreground/40',
        )}
      />
    </Button>
  )
}
