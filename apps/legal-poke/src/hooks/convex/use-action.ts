import type { DefaultError, UseMutationOptions } from '@tanstack/react-query'
import type {
  FunctionArgs,
  FunctionReference,
  FunctionReturnType,
} from 'convex/server'

import { useConvexAction } from '@convex-dev/react-query'
import { useMutation } from '@tanstack/react-query'

import { useConvexAuthGate } from './auth'

type PokeActionOptions<TData, TVariables> = Omit<
  UseMutationOptions<TData, DefaultError, TVariables>,
  'mutationFn'
>

export function usePokeAction<TAction extends FunctionReference<'action'>>(
  action: TAction,
  options?: PokeActionOptions<
    FunctionReturnType<TAction>,
    FunctionArgs<TAction>
  >,
) {
  useConvexAuthGate()
  const actionFn = useConvexAction(action)

  return useMutation({
    mutationFn: (variables: FunctionArgs<TAction>) => actionFn(variables),
    ...options,
  })
}
