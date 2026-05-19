// Shared optimistic-mutation helper for the catalog's per-resource caches
// (gmail drafts, calendar events, future siblings). Encapsulates the
// cancelQueries + snapshot-previous + setQueryData(patch) on onMutate, and
// the snapshot restore on onError.
//
// TanStack Query does NOT auto-rollback — this helper IS the rollback.
// All catalog cache mutations route through here so the cancel/snapshot/
// restore pattern stays uniform across resource types.

import { useMutation, useQueryClient } from '@tanstack/react-query'

export type OptimisticMutationOptions<TCache, TData, TVars> = {
  // Server call that returns the canonical response payload.
  mutationFn: (vars: TVars) => Promise<TData>
  // Unique mutationKey for this op (helps TanStack dedupe in-flight mutations).
  mutationKey: readonly unknown[]
  // Patch applied after the server confirms success. Use for fields the
  // server is authoritative over (e.g. rotated id).
  onSuccess?: (response: TData, current: TCache) => Partial<TCache> | undefined
  // Patch applied to the cached value during onMutate. Skipped when the
  // cache has no existing entry (avoids polluting unrelated drafts/events).
  optimistic?: (previous: TCache, vars: TVars) => Partial<TCache>
  // The TanStack cache key the optimistic patch targets.
  queryKey: readonly unknown[]
}

export function useOptimisticMutation<TCache, TData, TVars = void>(
  opts: OptimisticMutationOptions<TCache, TData, TVars>,
) {
  const queryClient = useQueryClient()
  const { onSuccess: onSuccessPatch, queryKey } = opts

  return useMutation<TData, Error, TVars, { previous: TCache | undefined }>({
    mutationFn: opts.mutationFn,
    mutationKey: opts.mutationKey,
    onError: (_error, _vars, context) => {
      if (context?.previous !== undefined) {
        queryClient.setQueryData(queryKey, context.previous)
      }
    },
    onMutate: async (vars) => {
      await queryClient.cancelQueries({ queryKey })
      const previous = queryClient.getQueryData<TCache>(queryKey)
      if (previous && opts.optimistic) {
        const patch = opts.optimistic(previous, vars)
        queryClient.setQueryData<TCache>(queryKey, { ...previous, ...patch })
      }
      return { previous }
    },
    onSuccess: onSuccessPatch
      ? (data) => {
          queryClient.setQueryData<TCache | undefined>(queryKey, (current) => {
            if (!current) return current
            const patch = onSuccessPatch(data, current)
            return patch ? { ...current, ...patch } : current
          })
        }
      : undefined,
  })
}
