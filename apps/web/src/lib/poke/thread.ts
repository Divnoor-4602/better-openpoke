import type {
  PageQuery,
  ThreadResource,
  ThreadUpdateRequest,
} from '@openpoke/sdk'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { poke } from './client'

type RenameThreadInput = {
  title: ThreadUpdateRequest['title']
}

export const threadKeys = {
  all: ['threads'] as const,
  detail: (threadId: string) =>
    [...threadKeys.all, 'detail', threadId] as const,
  lists: () => [...threadKeys.all, 'list'] as const,
  messages: (threadId: string) =>
    [...threadKeys.detail(threadId), 'messages'] as const,
}

export const threadMutationKeys = {
  create: [...threadKeys.all, 'create'] as const,
  delete: (threadId: string) =>
    [...threadKeys.detail(threadId), 'delete'] as const,
  update: (threadId: string) =>
    [...threadKeys.detail(threadId), 'update'] as const,
}

export function useCreateThreadMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async () => {
      const { data } = await poke.threads.create()
      return data.thread
    },
    mutationKey: threadMutationKeys.create,
    onSuccess: (thread) => {
      setThreadInCache(queryClient, thread)
      void queryClient.invalidateQueries({ queryKey: threadKeys.lists() })
    },
  })
}

export function useDeleteThreadMutation(threadId: string) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async () => {
      const { data } = await poke.threads.delete(threadId)
      return data
    },
    mutationKey: threadMutationKeys.delete(threadId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: threadKeys.all })
    },
  })
}

export function useThread(threadId: null | string) {
  return useQuery({
    enabled: Boolean(threadId),
    queryFn: async () => {
      if (!threadId) throw new Error('Missing thread id')
      const { data } = await poke.threads.retrieve(threadId)
      return data.thread
    },
    queryKey: threadId
      ? threadKeys.detail(threadId)
      : [...threadKeys.all, 'detail', null],
  })
}

export function useThreadMessages(threadId: null | string, query?: PageQuery) {
  return useQuery({
    enabled: Boolean(threadId),
    queryFn: async () => {
      if (!threadId) throw new Error('Missing thread id')
      const { data } = await poke.threads.messages.list(threadId, query)
      return data
    },
    queryKey: threadId
      ? [...threadKeys.messages(threadId), query]
      : [...threadKeys.all, 'messages', null, query],
  })
}

export function useThreads(query?: PageQuery) {
  return useQuery({
    queryFn: async () => {
      const { data } = await poke.threads.list(query)
      return data
    },
    queryKey: [...threadKeys.lists(), query] as const,
  })
}

export function useUpdateThreadMutation(threadId: null | string) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ title }: RenameThreadInput) => {
      if (!threadId) throw new Error('Missing thread id')
      const { data } = await poke.threads.update(threadId, { title })
      return data.thread
    },
    mutationKey: threadMutationKeys.update(threadId ?? 'inactive'),
    onSuccess: (thread) => {
      setThreadInCache(queryClient, thread)
      void queryClient.invalidateQueries({ queryKey: threadKeys.lists() })
    },
  })
}

function setThreadInCache(
  queryClient: ReturnType<typeof useQueryClient>,
  thread: ThreadResource,
) {
  queryClient.setQueryData(threadKeys.detail(thread.threadId), thread)
}
