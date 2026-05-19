import type { ComponentType } from 'react'

import type { NormalizedToolCall } from '../../lib/agent-state'

export type CatalogComponent = ComponentType<CatalogComponentProps>

export type CatalogComponentProps = { call: NormalizedToolCall }

export type CatalogEntry = {
  readonly Component: CatalogComponent
  readonly placement: CatalogPlacement
}

export type CatalogPlacement = 'block' | 'inline'
