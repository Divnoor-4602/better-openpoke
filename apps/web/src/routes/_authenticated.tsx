import { getAuthToken, retrieveMe } from '@openpoke/sdk'
import { createFileRoute, Outlet, redirect } from '@tanstack/react-router'

import { authKeys } from '@/lib/poke/auth'

export const Route = createFileRoute('/_authenticated')({
  beforeLoad: async ({ context }) => {
    if (typeof window === 'undefined') return { workspaceId: null }

    if (!getAuthToken()) throw redirect({ to: '/login' })
    try {
      const me = await context.queryClient.ensureQueryData({
        queryFn: async () => {
          const { data } = await retrieveMe({ throwOnError: true })
          return data
        },
        queryKey: authKeys.me(),
        retry: false,
        staleTime: 60_000,
      })
      return { workspaceId: me.workspaceId }
    } catch {
      throw redirect({ to: '/login' })
    }
  },
  component: Outlet,
})
