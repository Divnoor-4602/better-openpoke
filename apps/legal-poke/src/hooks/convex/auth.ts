import { useConvexAuth } from 'convex/react'

export class AuthRequiredError extends Error {
  override readonly name = 'AuthRequiredError'

  constructor(message = 'Authentication required') {
    super(message)
  }
}

// Render-time throw bubbles to the nearest route `errorComponent`.
export function useConvexAuthGate(): void {
  const { isAuthenticated, isLoading } = useConvexAuth()

  if (!isLoading && !isAuthenticated) {
    throw new AuthRequiredError()
  }
}
