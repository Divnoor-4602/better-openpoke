import * as React from 'react'

import { Input } from '@general-poke/ui/components/input'
import { cn } from '@/lib/utils'

type AuthInputProps = React.ComponentProps<'input'> & {
  error?: string
  label: string
}

export const AuthInput = ({
  className,
  error,
  id,
  label,
  ...props
}: AuthInputProps) => {
  const reactId = React.useId()
  const inputId = id ?? reactId
  const errorId = `${inputId}-error`

  return (
    <div className="flex flex-col gap-2">
      <label className="text-13 font-normal text-stone-400" htmlFor={inputId}>
        {label}
      </label>
      <Input
        aria-describedby={error ? errorId : undefined}
        aria-invalid={error ? 'true' : undefined}
        id={inputId}
        {...props}
        className={cn(
          'h-10 rounded-poke bg-white border text-sm! px-4',
          className,
        )}
      />
      {error ? (
        <p className="text-destructive text-xs" id={errorId}>
          {error}
        </p>
      ) : null}
    </div>
  )
}
