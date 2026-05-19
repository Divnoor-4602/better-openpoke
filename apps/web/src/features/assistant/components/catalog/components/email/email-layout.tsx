import type { ReactNode } from 'react'

import { EnvelopeIcon } from '@phosphor-icons/react'

import type { DraftEmailDiscardButtonProps } from './email-discard-button'

import { DraftEmailDiscardButton } from './email-discard-button'

export const DraftEmailShell = ({ children }: { children: ReactNode }) => {
  return (
    <div className="w-full max-w-lg rounded-poke border bg-white py-4">
      {children}
    </div>
  )
}

type DraftEmailHeaderProps = {
  discard?: DraftEmailDiscardButtonProps
}

export const DraftEmailHeader = ({ discard }: DraftEmailHeaderProps) => {
  return (
    <div className="flex items-center justify-between border-b border-border px-4 pb-3 shadow-none">
      <div className="flex items-center gap-1">
        <EnvelopeIcon />
        <span className="text-13 font-normal">Compose Email</span>
      </div>
      <DraftEmailDiscardButton {...(discard ?? {})} />
    </div>
  )
}

export const DraftEmailContent = ({ children }: { children: ReactNode }) => {
  return <div className="flex flex-col gap-4 pt-4">{children}</div>
}
