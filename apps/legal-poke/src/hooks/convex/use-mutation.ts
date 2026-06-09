import type { DefaultError, UseMutationOptions } from '@tanstack/react-query'
import type {
  FunctionArgs,
  FunctionReference,
  FunctionReturnType,
} from 'convex/server'

import { useConvexMutation } from '@convex-dev/react-query'
import { useMutation } from '@tanstack/react-query'

import { useConvexAuthGate } from './auth'

type PokeMutationOptions<TData, TVariables> = Omit<
  UseMutationOptions<TData, DefaultError, TVariables>,
  'mutationFn'
>

export function usePokeMutation<
  TMutation extends FunctionReference<'mutation'>,
>(
  mutation: TMutation,
  options?: PokeMutationOptions<
    FunctionReturnType<TMutation>,
    FunctionArgs<TMutation>
  >,
) {
  useConvexAuthGate()
  const mutationFn = useConvexMutation(mutation)

  return useMutation({
    mutationFn: (variables: FunctionArgs<TMutation>) => mutationFn(variables),
    ...options,
  })
}
