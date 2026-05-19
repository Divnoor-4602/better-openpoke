import type { QueryClient } from '@tanstack/react-query'

import { TanStackDevtools } from '@tanstack/react-devtools'
import {
  createRootRouteWithContext,
  HeadContent,
  Scripts,
} from '@tanstack/react-router'
import { TanStackRouterDevtoolsPanel } from '@tanstack/react-router-devtools'

import { Toaster } from '@/components/ui/sonner'

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
