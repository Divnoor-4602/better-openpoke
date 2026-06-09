import { defineSchema } from 'convex/server'

import { User } from './user/validator'

export default defineSchema({
  users: User.table.index('by_clerkId', ['clerkId']),
})
