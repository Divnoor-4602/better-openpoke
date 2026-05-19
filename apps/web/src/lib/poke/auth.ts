import type { MeResponse } from '@openpoke/sdk'

import { retrieveMe, setAuthToken } from '@openpoke/sdk'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

const STORAGE_KEY = 'openpoke.basic'

export const authKeys = {
  all: ['auth'] as const,
  me: () => [...authKeys.all, 'me'] as const,
}

export const authMutationKeys = {
  login: [...authKeys.all, 'login'] as const,
  logout: [...authKeys.all, 'logout'] as const,
}

const readToken = (): null | string => {
  if (typeof window === 'undefined') return null
  return window.localStorage.getItem(STORAGE_KEY)
}

const writeToken = (token: null | string) => {
  if (typeof window === 'undefined') return
  if (token) window.localStorage.setItem(STORAGE_KEY, token)
  else window.localStorage.removeItem(STORAGE_KEY)
}

export const hydrateCredentialsFromStorage = () => {
  setAuthToken(readToken())
}

const fetchMe = async (): Promise<MeResponse> => {
  const { data } = await retrieveMe({ throwOnError: true })
  return data
}

export const useMe = () =>
  useQuery({
    queryFn: fetchMe,
    queryKey: authKeys.me(),
    retry: false,
    staleTime: 60_000,
  })

export const useLogin = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (input: { handle: string; password: string }) => {
      const token = window.btoa(`${input.handle}:${input.password}`)
      setAuthToken(token)
      try {
        const me = await fetchMe()
        writeToken(token)
        return me
      } catch (error) {
        setAuthToken(null)
        throw error
      }
    },
    mutationKey: authMutationKeys.login,
    onSuccess: (data) => {
      queryClient.setQueryData(authKeys.me(), data)
    },
  })
}

export const onUnauthorized = () => {
  writeToken(null)
  setAuthToken(null)
  if (typeof window !== 'undefined' && window.location.pathname !== '/login') {
    window.location.assign('/login')
  }
}

export const useLogout = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      writeToken(null)
      setAuthToken(null)
    },
    mutationKey: authMutationKeys.logout,
    onSuccess: () => {
      queryClient.removeQueries()
    },
  })
}
