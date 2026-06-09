import type { UserJSON } from '@clerk/backend'

import type { QueryCtx } from '../_generated/server'
import type { TUser } from './validator'

import { validationError } from '../error'

export async function getUserByClerkId(
  ctx: QueryCtx,
  clerkId: string,
): Promise<null | TUser> {
  return await ctx.db
    .query('users')
    .withIndex('by_clerkId', (q) => q.eq('clerkId', clerkId))
    .unique()
}

export function primaryEmail(data: UserJSON): string {
  const primary = data.email_addresses.find(
    (e) => e.id === data.primary_email_address_id,
  )
  const email = primary?.email_address ?? data.email_addresses[0]?.email_address
  if (!email) {
    validationError({
      entity: 'User',
      id: data.id,
      message: 'Clerk user has no email address',
    })
  }
  return email
}
