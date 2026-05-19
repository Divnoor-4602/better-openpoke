import { MutationCache, QueryCache, QueryClient } from '@tanstack/react-query'

import { hydrateCredentialsFromStorage, onUnauthorized } from '@/lib/poke/auth'

const isUnauthorized = (error: unknown) =>
  (error instanceof Response && error.status === 401) ||
  (typeof error === 'object' &&
    error !== null &&
    'status' in error &&
    (error as { status?: number }).status === 401)

export function getContext() {
  hydrateCredentialsFromStorage()
  const queryClient = new QueryClient({
    mutationCache: new MutationCache({
      onError: (error) => {
        if (isUnauthorized(error)) onUnauthorized()
      },
    }),
    queryCache: new QueryCache({
      onError: (error) => {
        if (isUnauthorized(error)) onUnauthorized()
      },
    }),
  })

  return {
    queryClient,
  }
}
export default function TanstackQueryProvider() {}
