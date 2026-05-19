import { getAuthToken, retrieveMe } from '@openpoke/sdk'
import { createFileRoute, redirect } from '@tanstack/react-router'

import { LoginLayout } from '@/features/auth/components/login-layout'
import { authKeys } from '@/lib/poke/auth'

export const Route = createFileRoute('/login')({
  beforeLoad: async ({ context }) => {
    if (typeof window === 'undefined') return

    if (!getAuthToken()) return

    try {
      await context.queryClient.ensureQueryData({
        queryFn: async () => {
          const { data } = await retrieveMe({ throwOnError: true })
          return data
        },
        queryKey: authKeys.me(),
        retry: false,
        staleTime: 60_000,
      })
    } catch {
      return
    }
    throw redirect({ to: '/' })
  },
  component: LoginLayout,
})
