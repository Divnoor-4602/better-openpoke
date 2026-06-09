import type { AnchorHTMLAttributes } from 'react'

import { cn } from '@general-poke/ui'
import { ArrowUpRightIcon } from '@phosphor-icons/react'

type StreamdownLinkProps = AnchorHTMLAttributes<HTMLAnchorElement> & {
  node?: unknown
}

export const StreamdownLink = ({
  children,
  className,
  href,
  node: _node,
  ...props
}: StreamdownLinkProps) => {
  const isExternal = href ? /^https?:\/\//.test(href) : false

  return (
    <a
      className={cn(
        'group/link rounded-sm font-normal text-foreground underline decoration-muted-foreground/40 underline-offset-4 transition-colors hover:decoration-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/30 text-sm',
        className,
      )}
      href={href}
      rel={isExternal ? 'noopener noreferrer' : undefined}
      target={isExternal ? '_blank' : undefined}
      {...props}
    >
      {children}{' '}
      <ArrowUpRightIcon className="inline-block size-3 mb-1 -ml-0.5 text-muted-foreground transition-colors group-hover/link:text-foreground mr-1" />
    </a>
  )
}
