import { ConvexQueryClient } from '@convex-dev/react-query'
import { QueryClient } from '@tanstack/react-query'
import { ConvexReactClient } from 'convex/react'

export interface RouterContext {
  convexClient: ConvexReactClient
  convexQueryClient: ConvexQueryClient
  queryClient: QueryClient
}

export function getContext(): RouterContext {
  const convexUrl = import.meta.env.VITE_CONVEX_URL

  if (!convexUrl) {
    throw new Error('missing VITE_CONVEX_URL envar')
  }

  const convexClient = new ConvexReactClient(convexUrl, {
    unsavedChangesWarning: false,
  })
  const convexQueryClient = new ConvexQueryClient(convexClient)

  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        queryFn: convexQueryClient.queryFn(),
        queryKeyHashFn: convexQueryClient.hashFn(),
      },
    },
  })

  convexQueryClient.connect(queryClient)

  return {
    convexClient,
    convexQueryClient,
    queryClient,
  }
}

export default function TanstackQueryProvider() {}
