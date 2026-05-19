import * as React from 'react'

import { Input } from '@/components/ui/input'

type AuthInputProps = React.ComponentProps<'input'> & {
  error?: string
  label: string
}

export const AuthInput = ({ error, id, label, ...props }: AuthInputProps) => {
  return (
    <div className="flex flex-col gap-2">
      <label className="text-13 font-normal text-stone-400" htmlFor={id}>
        {label}
      </label>
      <Input
        aria-invalid={error ? 'true' : undefined}
        id={id}
        {...props}
        className="h-10 rounded-poke bg-white border text-sm! px-4"
      />
      {error ? <p className="text-destructive text-xs">{error}</p> : null}
    </div>
  )
}
