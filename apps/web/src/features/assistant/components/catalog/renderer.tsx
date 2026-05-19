import { cn } from '@/lib/utils'

import type { MessageBlock } from '../../lib/agent-state'

import { getCatalogEntry } from './registry'

type CatalogRendererProps = {
  block: Extract<MessageBlock, { type: 'catalog' }>
  integrationPrompt?: React.ComponentType<{ message?: string }>
}

export const CatalogRenderer = ({
  block,
  integrationPrompt: IntegrationPrompt,
}: CatalogRendererProps) => {
  const wrapperClassName = cn(
    block.placement === 'inline' ? 'inline-flex items-center' : 'my-2',
  )

  if (block.variant.kind === 'integrations-button') {
    return (
      <div className={wrapperClassName}>
        {IntegrationPrompt ? (
          <IntegrationPrompt message={block.variant.message} />
        ) : null}
      </div>
    )
  }

  const entry = getCatalogEntry(block.variant.call.toolName)
  if (!entry) return null
  const { Component } = entry
  return (
    <div className={wrapperClassName}>
      <Component call={block.variant.call} />
    </div>
  )
}
