import { NotePencilIcon } from '@phosphor-icons/react'
import { useNavigate } from '@tanstack/react-router'

import { Button } from '@/components/ui/button'
import { TooltipTrigger } from '@/components/ui/tooltip'

type NewThreadButtonProps = {
  handle?: TooltipHandle
}

type TooltipHandle = React.ComponentProps<typeof TooltipTrigger>['handle']

export const NewThreadButton = ({ handle }: NewThreadButtonProps) => {
  const navigate = useNavigate()
  return (
    <TooltipTrigger
      handle={handle}
      payload="New thread"
      render={
        <Button
          aria-label="New thread"
          onClick={() => {
            void navigate({ to: '/threads/new' })
          }}
          size="icon-sm"
          variant="ghost"
        />
      }
    >
      <NotePencilIcon />
    </TooltipTrigger>
  )
}
