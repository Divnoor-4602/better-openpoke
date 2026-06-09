import {
  customAction,
  customCtx,
  customMutation,
  customQuery,
} from 'convex-helpers/server/customFunctions'

import type { QueryCtx } from './_generated/server'
import type { TUser, TUserId } from './user/validator'

import { action, mutation, query } from './_generated/server'
import { validationError } from './error'
import { getUserByClerkId } from './user/helpers'

async function requireUser(ctx: QueryCtx): Promise<TUser> {
  const identity = await ctx.auth.getUserIdentity()

  if (!identity)
    validationError({ entity: 'User', message: 'Not authenticated' })

  const user = await getUserByClerkId(ctx, identity.subject)

  if (!user) {
    validationError({
      entity: 'User',
      id: identity.subject,
      message: 'User row missing for authenticated identity',
    })
  }

  return user
}

export const pokeQuery = customQuery(
  query,
  customCtx(async (ctx) => ({ user: await requireUser(ctx) })),
)

export const pokeMutation = customMutation(
  mutation,
  customCtx(async (ctx) => ({ user: await requireUser(ctx) })),
)

export const pokeAction = customAction(
  action,
  customCtx(async (ctx) => {
    const identity = await ctx.auth.getUserIdentity()
    if (!identity)
      validationError({ entity: 'User', message: 'Not authenticated' })
    return { clerkId: identity.subject }
  }),
)

export function assertAuthorized<T extends { userId: TUserId }>(
  user: TUser,
  resource: null | T | undefined,
  entity?: string,
): asserts resource is T {
  if (!isAuthorized(user, resource)) {
    validationError({ entity, message: 'Not authorized' })
  }
}

export function isAuthorized<T extends { userId: TUserId }>(
  user: TUser,
  resource: null | T | undefined,
): resource is T {
  return !!resource && resource.userId === user._id
}
