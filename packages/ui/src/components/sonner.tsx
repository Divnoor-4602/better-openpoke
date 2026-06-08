import type { CSSProperties } from 'react'
import type { ToasterProps } from 'sonner'

import {
  CheckCircleIcon,
  InfoIcon,
  SpinnerIcon,
  WarningIcon,
  XCircleIcon,
} from '@phosphor-icons/react'
import { Toaster as Sonner } from 'sonner'

const Toaster = ({ ...props }: ToasterProps) => {
  return (
    <Sonner
      className="toaster group"
      icons={{
        error: <XCircleIcon className="size-4" />,
        info: <InfoIcon className="size-4" />,
        loading: <SpinnerIcon className="size-4 animate-spin" />,
        success: <CheckCircleIcon className="size-4" />,
        warning: <WarningIcon className="size-4" />,
      }}
      style={
        {
          '--border-radius': 'var(--radius)',
          '--normal-bg': 'var(--popover)',
          '--normal-border': 'var(--border)',
          '--normal-text': 'var(--popover-foreground)',
          '--width': '22rem',
        } as CSSProperties
      }
      theme="light"
      toastOptions={{
        classNames: {
          actionButton:
            'group-[.toaster]:h-6 group-[.toaster]:rounded-md group-[.toaster]:border group-[.toaster]:border-input group-[.toaster]:bg-popover group-[.toaster]:px-2 group-[.toaster]:text-xs group-[.toaster]:font-medium group-[.toaster]:text-foreground group-[.toaster]:shadow-xs/5 group-[.toaster]:transition-colors group-[.toaster]:hover:bg-accent/50',
          cancelButton:
            'group-[.toaster]:h-6 group-[.toaster]:rounded-md group-[.toaster]:bg-muted group-[.toaster]:px-2 group-[.toaster]:text-xs group-[.toaster]:font-medium group-[.toaster]:text-muted-foreground group-[.toaster]:transition-colors group-[.toaster]:hover:bg-muted/80',
          closeButton:
            'group-[.toaster]:border-border group-[.toaster]:bg-popover group-[.toaster]:text-muted-foreground group-[.toaster]:shadow-xs/5 group-[.toaster]:transition-colors group-[.toaster]:hover:bg-accent group-[.toaster]:hover:text-foreground',
          content: 'group-[.toaster]:gap-0.5',
          description:
            'group-[.toaster]:text-xs/relaxed group-[.toaster]:text-muted-foreground',
          error: 'group-[.toaster]:[&_[data-icon]]:text-destructive',
          icon: 'group-[.toaster]:text-muted-foreground',
          info: 'group-[.toaster]:[&_[data-icon]]:text-primary',
          loading: 'group-[.toaster]:[&_[data-icon]]:text-muted-foreground',
          success: 'group-[.toaster]:[&_[data-icon]]:text-primary',
          title:
            'group-[.toaster]:text-xs/relaxed group-[.toaster]:font-medium',
          toast:
            'group-[.toaster]:min-h-12 group-[.toaster]:items-start group-[.toaster]:gap-2.5 group-[.toaster]:rounded-lg group-[.toaster]:border-border group-[.toaster]:bg-popover group-[.toaster]:px-3 group-[.toaster]:py-2.5 group-[.toaster]:text-popover-foreground group-[.toaster]:shadow-md group-[.toaster]:ring-1 group-[.toaster]:ring-foreground/10 group-[.toaster]:[&_[data-icon]]:mt-0.5 group-[.toaster]:[&_[data-icon]]:shrink-0',
          warning: 'group-[.toaster]:[&_[data-icon]]:text-primary',
        },
      }}
      {...props}
    />
  )
}

export { Toaster }
