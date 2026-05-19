import type { ComponentType } from 'react'
import type { z, ZodType } from 'zod'

import type { CatalogComponent } from './types'

export const fromInput = <TSchema extends ZodType>(
  Component: ComponentType<z.infer<TSchema>>,
  schema: TSchema,
  options: {
    mapOutput?: (output: unknown) => Partial<z.infer<TSchema>>
  } = {},
): CatalogComponent => {
  const Adapter: CatalogComponent = ({ call }) => {
    const result = schema.safeParse(call.input ?? {})
    const inputProps = (result.success ? result.data : {}) as Record<
      string,
      unknown
    > &
      z.infer<TSchema>
    const outputProps =
      options.mapOutput && call.output !== undefined
        ? options.mapOutput(call.output)
        : undefined
    if (!outputProps) return <Component {...inputProps} />
    const merged = { ...inputProps, ...outputProps }
    return <Component {...merged} />
  }
  Adapter.displayName = `fromInput(${Component.displayName || Component.name || 'Component'})`
  return Adapter
}
