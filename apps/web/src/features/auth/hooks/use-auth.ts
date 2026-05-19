import { useNavigate } from '@tanstack/react-router'

import { useLogin, useLogout, useMe } from '@/lib/poke/auth'

export type AuthStatus =
  | 'authenticated'
  | 'checking'
  | 'error'
  | 'unauthenticated'

export const useAuth = () => {
  const navigate = useNavigate()
  const meQuery = useMe()
  const loginMutation = useLogin()
  const logoutMutation = useLogout()

  const status: AuthStatus = meQuery.isPending
    ? 'checking'
    : meQuery.isError
      ? 'unauthenticated'
      : meQuery.data
        ? 'authenticated'
        : 'unauthenticated'

  return {
    isAuthenticated: status === 'authenticated',
    isChecking: meQuery.isPending,
    login: async (handle: string, password: string) => {
      await loginMutation.mutateAsync({ handle, password })
      await navigate({ to: '/' })
    },
    loginMutation,
    logout: async () => {
      await logoutMutation.mutateAsync()
      await navigate({ replace: true, to: '/login' })
    },
    logoutMutation,
    meQuery,
    status,
    workspaceId: meQuery.data?.workspaceId ?? null,
  }
}
