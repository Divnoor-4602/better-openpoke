import { useIsMutating } from '@tanstack/react-query'
import { useLocation } from '@tanstack/react-router'

import {
  googleIntegrationMutationKeys,
  useConnectGoogleIntegration,
  useDisconnectGoogleIntegration,
  useGoogleIntegrationStatus,
  useReconnectGoogleIntegration,
} from '@/lib/poke/integrations'

export type GoogleIntegrationStatus =
  | 'checking'
  | 'connected'
  | 'connecting'
  | 'disconnecting'
  | 'error'
  | 'idle'

export function getGoogleIntegrationLabel(status: GoogleIntegrationStatus) {
  if (status === 'connected') return 'Connected'
  if (status === 'connecting') return 'Connecting...'
  if (status === 'disconnecting') return 'Disconnecting...'
  if (status === 'error') return 'Try again'
  return 'Connect to Google'
}

export function useGoogleIntegration() {
  const location = useLocation()
  const statusQuery = useGoogleIntegrationStatus()
  const connectMutation = useConnectGoogleIntegration()
  const disconnectMutation = useDisconnectGoogleIntegration()
  const reconnectMutation = useReconnectGoogleIntegration()

  const activeConnectMutations = useIsMutating({
    mutationKey: googleIntegrationMutationKeys.connect,
  })
  const activeDisconnectMutations = useIsMutating({
    mutationKey: googleIntegrationMutationKeys.disconnect,
  })
  const activeReconnectMutations = useIsMutating({
    mutationKey: googleIntegrationMutationKeys.reconnect,
  })

  const connected = statusQuery.data?.connected ?? false
  const email = statusQuery.data?.email ?? null
  const getReturnTo = () => new URL(location.href, window.location.origin).href

  const isConnecting =
    connectMutation.isPending ||
    reconnectMutation.isPending ||
    activeConnectMutations > 0 ||
    activeReconnectMutations > 0
  const isDisconnecting =
    disconnectMutation.isPending || activeDisconnectMutations > 0
  const isChecking = statusQuery.isPending
  const hasError =
    statusQuery.isError ||
    connectMutation.isError ||
    disconnectMutation.isError ||
    reconnectMutation.isError

  const status: GoogleIntegrationStatus = connected
    ? 'connected'
    : isConnecting
      ? 'connecting'
      : isDisconnecting
        ? 'disconnecting'
        : hasError
          ? 'error'
          : isChecking
            ? 'checking'
            : 'idle'

  const connect = () => {
    connectMutation.mutate({ returnTo: getReturnTo() })
  }

  const disconnect = () => {
    disconnectMutation.mutate({
      userId: statusQuery.data?.userId,
    })
  }

  const reconnect = () => {
    reconnectMutation.mutate({
      disconnect: {
        userId: statusQuery.data?.userId,
      },
      returnTo: getReturnTo(),
    })
  }

  return {
    connect,
    connected,
    connectMutation,
    disconnect,
    disconnectMutation,
    email,
    isBusy: isConnecting || isDisconnecting,
    isChecking,
    isConnecting,
    isDisconnecting,
    reconnect,
    reconnectMutation,
    status,
    statusQuery,
  }
}
