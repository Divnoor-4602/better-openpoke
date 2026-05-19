import type {
  DraftDiscardResponse,
  DraftSendResponse,
  DraftUpdateResponse,
} from '@openpoke/sdk'

import { useQuery, useQueryClient } from '@tanstack/react-query'

import type { SendDraftPatch } from '@/features/assistant/components/catalog/schemas'

import { useOptimisticMutation } from '@/features/assistant/components/catalog/hooks/use-optimistic-mutation'
import { stripUndefined } from '@/lib/utils'

import { poke } from './client'

export type { SendDraftPatch } from '@/features/assistant/components/catalog/schemas'

export const gmailDraftKeys = {
  all: ['gmail', 'drafts'] as const,
  byId: (draftId: string) => [...gmailDraftKeys.all, draftId],
}

export const gmailDraftMutationKeys = {
  discard: (draftId: string) => [...gmailDraftKeys.byId(draftId), 'discard'],
  send: (draftId: string) => [...gmailDraftKeys.byId(draftId), 'send'],
  update: (draftId: string) => [...gmailDraftKeys.byId(draftId), 'update'],
}

export type DraftCacheValue = {
  bcc?: string[]
  body?: string
  cc?: string[]
  draftId: string
  status: 'discarded' | 'idle' | 'sending' | 'sent'
  subject?: string
  to?: string
}

export type DraftEditableFields = SendDraftPatch

export function useDiscardDraft(draftId: string) {
  return useOptimisticMutation<DraftCacheValue, DraftDiscardResponse>({
    mutationFn: async () => {
      const { data } = await poke.gmail.drafts.discard({ draftId })
      return data
    },
    mutationKey: gmailDraftMutationKeys.discard(draftId),
    optimistic: () => ({ status: 'discarded' }),
    queryKey: gmailDraftKeys.byId(draftId),
  })
}

export function useDraft(draftId: string, initial: DraftCacheValue) {
  const queryClient = useQueryClient()
  const queryKey = gmailDraftKeys.byId(draftId)
  // Seed under any cache value useGoogleSync wrote before mount. Read
  // (don't write) — the render-time setQueryData we had here used to
  // notify subscribers and re-render in a loop. React Compiler memoizes
  // `seeded`; TanStack ignores `initialData` once a value is cached.
  const existing = queryClient.getQueryData<Partial<DraftCacheValue>>(queryKey)
  const seeded: DraftCacheValue = { ...initial, ...(existing ?? {}) }
  return useQuery<DraftCacheValue>({
    gcTime: Infinity,
    initialData: seeded,
    queryFn: () => Promise.resolve(seeded),
    queryKey,
    staleTime: Infinity,
  })
}

export function useSendDraft(draftId: string) {
  return useOptimisticMutation<DraftCacheValue, DraftSendResponse>({
    mutationFn: async () => {
      const { data } = await poke.gmail.drafts.send({ draftId })
      return data
    },
    mutationKey: gmailDraftMutationKeys.send(draftId),
    onSuccess: () => ({ status: 'sent' }),
    optimistic: () => ({ status: 'sending' }),
    queryKey: gmailDraftKeys.byId(draftId),
  })
}

export function useUpdateDraft(draftId: string) {
  return useOptimisticMutation<
    DraftCacheValue,
    DraftUpdateResponse,
    DraftEditableFields
  >({
    mutationFn: async (fields) => {
      const { data } = await poke.gmail.drafts.update({
        draftId,
        ...stripUndefined(fields),
      })
      return data
    },
    mutationKey: gmailDraftMutationKeys.update(draftId),
    onSuccess: (response) => ({ draftId: response.draftId }),
    optimistic: (_previous, fields) => stripUndefined(fields),
    queryKey: gmailDraftKeys.byId(draftId),
  })
}
