import type { Infer } from 'convex/values'

import { Table } from 'convex-helpers/server'
import { v } from 'convex/values'

import { User } from '../user/validators'

export const vOauthProvider = v.union(v.literal('google'))

export const vOauthState = v.object({
  createdAt: v.number(),
  expiresAt: v.number(),
  provider: vOauthProvider,
  state: v.string(),
  userId: User._id,
})

export const OauthState = Table('oauthStates', vOauthState.fields)

export type TOauthProvider = Infer<typeof vOauthProvider>
export type TOauthState = Infer<typeof OauthState.doc>
export type TOauthStateId = Infer<typeof OauthState._id>
