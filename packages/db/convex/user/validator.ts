import type { Infer } from 'convex/values'

import { Table } from 'convex-helpers/server'
import { v } from 'convex/values'

export const vUser = v.object({
  clerkId: v.string(),
  email: v.string(),
})

export const User = Table('users', vUser.fields)

export type TUser = Infer<typeof User.doc>

export type TUserId = Infer<typeof User._id>
