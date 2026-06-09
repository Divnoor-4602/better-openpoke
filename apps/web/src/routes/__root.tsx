import type { QueryClient } from '@tanstack/react-query'

import { Toaster } from '@general-poke/ui/components/sonner'
import { TanStackDevtools } from '@tanstack/react-devtools'
import {
  createRootRouteWithContext,
  HeadContent,
  Scripts,
} from '@tanstack/react-router'
import { TanStackRouterDevtoolsPanel } from '@tanstack/react-router-devtools'

import TanStackQueryDevtools from '../lib/tanstack-query/devtools'
import appCss from '../styles.css?url'

interface MyRouterContext {
  queryClient: QueryClient
}

export const Route = createRootRouteWithContext<MyRouterContext>()({
  head: () => ({
    links: [
      {
        href: appCss,
        rel: 'stylesheet',
      },
      {
        href: '/favicon-light.svg',
        media: '(prefers-color-scheme: light)',
        rel: 'icon',
        type: 'image/svg+xml',
      },
      {
        href: '/favicon-dark.svg',
        media: '(prefers-color-scheme: dark)',
        rel: 'icon',
        type: 'image/svg+xml',
      },
      {
        href: '/favicon-96x96-light.png',
        media: '(prefers-color-scheme: light)',
        rel: 'icon',
        sizes: '96x96',
        type: 'image/png',
      },
      {
        href: '/favicon-96x96-dark.png',
        media: '(prefers-color-scheme: dark)',
        rel: 'icon',
        sizes: '96x96',
        type: 'image/png',
      },
      {
        href: '/favicon.ico',
        rel: 'shortcut icon',
      },
      {
        href: '/apple-touch-icon-dark.png',
        rel: 'apple-touch-icon',
        sizes: '180x180',
      },
      {
        href: '/manifest.json',
        rel: 'manifest',
      },
    ],
    meta: [
      {
        charSet: 'utf-8',
      },
      {
        content: 'width=device-width, initial-scale=1',
        name: 'viewport',
      },
      {
        title: 'General Poke',
      },
    ],
  }),
  shellComponent: RootDocument,
})

function RootDocument({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <HeadContent />
      </head>
      <body>
        {children}
        <Toaster closeButton position="bottom-right" />
        <TanStackDevtools
          config={{
            position: 'bottom-right',
          }}
          plugins={[
            {
              name: 'Tanstack Router',
              render: <TanStackRouterDevtoolsPanel />,
            },
            TanStackQueryDevtools,
          ]}
        />
        <Scripts />
      </body>
    </html>
  )
}
