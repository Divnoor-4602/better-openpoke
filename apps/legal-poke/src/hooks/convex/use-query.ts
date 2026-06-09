import type {
  DefaultError,
  UseQueryOptions,
  UseQueryResult,
} from '@tanstack/react-query'
import type {
  FunctionArgs,
  FunctionReference,
  FunctionReturnType,
} from 'convex/server'

import { convexQuery } from '@convex-dev/react-query'
import { useQuery } from '@tanstack/react-query'

import { useConvexAuthGate } from './auth'

type PokeQueryOptions<TData> = Omit<
  UseQueryOptions<TData, DefaultError, TData, readonly unknown[]>,
  'queryFn' | 'queryKey' | 'queryKeyHashFn'
>

export function usePokeQuery<TQuery extends FunctionReference<'query'>>(
  query: TQuery,
  args: FunctionArgs<TQuery>,
  options?: PokeQueryOptions<FunctionReturnType<TQuery>>,
): UseQueryResult<FunctionReturnType<TQuery>> {
  useConvexAuthGate()

  return useQuery({
    ...convexQuery(query, args),
    ...options,
  })
}
