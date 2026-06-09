import { Button } from '@general-poke/ui/components/button'
import { PaperclipIcon } from '@phosphor-icons/react'

export const AttachmentsButton = () => {
  return (
    <Button aria-label="Attach file" size={'icon'} variant={'outline'}>
      <PaperclipIcon className="size-4.5" />
    </Button>
  )
}
