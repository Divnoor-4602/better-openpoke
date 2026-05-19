import type {
  IntegrationConnectRequest,
  IntegrationDisconnectRequest,
} from '@openpoke/sdk'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { poke } from './client'

type ConnectGoogleInput = Pick<IntegrationConnectRequest, 'returnTo'>

type ReconnectGoogleInput = ConnectGoogleInput & {
  disconnect?: IntegrationDisconnectRequest
}

export const googleIntegrationKeys = {
  all: ['integrations', 'google'],
  status: () => [...googleIntegrationKeys.all, 'status'],
}

export const googleIntegrationMutationKeys = {
  connect: [...googleIntegrationKeys.all, 'connect'],
  disconnect: [...googleIntegrationKeys.all, 'disconnect'],
  reconnect: [...googleIntegrationKeys.all, 'reconnect'],
}

export function useConnectGoogleIntegration() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ returnTo }: ConnectGoogleInput) => {
      const { data } = await poke.integrations.google.connect({ returnTo })
      return data
    },
    mutationKey: googleIntegrationMutationKeys.connect,
    onSuccess: (data) => {
      if (data.redirectUrl) {
        window.location.assign(data.redirectUrl)
        return
      }

      void queryClient.invalidateQueries({
        queryKey: googleIntegrationKeys.all,
      })
    },
  })
}

export function useDisconnectGoogleIntegration() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (body: IntegrationDisconnectRequest = {}) => {
      const { data } = await poke.integrations.google.disconnect(body)
      return data
    },
    mutationKey: googleIntegrationMutationKeys.disconnect,
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: googleIntegrationKeys.all,
      })
    },
  })
}

export function useGoogleIntegrationStatus() {
  return useQuery({
    queryFn: async () => {
      const { data } = await poke.integrations.google.status({})
      return data
    },
    queryKey: googleIntegrationKeys.status(),
    refetchOnWindowFocus: true,
    staleTime: 30_000,
  })
}

export function useReconnectGoogleIntegration() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ disconnect, returnTo }: ReconnectGoogleInput) => {
      await poke.integrations.google.disconnect(disconnect ?? {})
      const { data } = await poke.integrations.google.connect({ returnTo })
      return data
    },
    mutationKey: googleIntegrationMutationKeys.reconnect,
    onSuccess: (data) => {
      void queryClient.invalidateQueries({
        queryKey: googleIntegrationKeys.all,
      })
      if (data.redirectUrl) {
        window.location.assign(data.redirectUrl)
      }
    },
  })
}
