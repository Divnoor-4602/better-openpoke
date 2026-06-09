import { getThreadMetadata, listUIMessages } from '@convex-dev/agent'
import { paginationOptsValidator } from 'convex/server'
import { v } from 'convex/values'

import { api, components } from '../../_generated/api'
import { pokeAction, pokeQuery } from '../../auth'
import { validationError } from '../../error'
import { legalAgent } from './base'

export const createThread = pokeAction({
  args: {
    prompt: v.string(),
    title: v.optional(v.string()),
  },
  handler: async (ctx, { prompt, title }) => {
    const user = await ctx.runQuery(api.public.user.queries.me, {})
    const { thread, threadId } = await legalAgent.createThread(ctx, {
      title,
      userId: user._id,
    })
    const result = await thread.generateText({ prompt })

    return { text: result.text, threadId }
  },
})

export const continueThread = pokeAction({
  args: {
    prompt: v.string(),
    threadId: v.string(),
  },
  handler: async (ctx, { prompt, threadId }) => {
    const user = await ctx.runQuery(api.public.user.queries.me, {})
    const { thread } = await legalAgent.continueThread(ctx, { threadId })
    const metadata = await thread.getMetadata()

    if (metadata.userId !== user._id) {
      validationError({ entity: 'AgentThread', message: 'Not authorized' })
    }

    const result = await thread.generateText({ prompt })

    return { text: result.text, threadId }
  },
})

export const listThreads = pokeQuery({
  args: { paginationOpts: paginationOptsValidator },
  handler: async (ctx, { paginationOpts }) => {
    return await ctx.runQuery(components.agent.threads.listThreadsByUserId, {
      paginationOpts,
      userId: ctx.user._id,
    })
  },
})

export const listMessages = pokeQuery({
  args: {
    paginationOpts: paginationOptsValidator,
    threadId: v.string(),
  },
  handler: async (ctx, { paginationOpts, threadId }) => {
    const metadata = await getThreadMetadata(ctx, components.agent, {
      threadId,
    })

    if (metadata.userId !== ctx.user._id) {
      validationError({ entity: 'AgentThread', message: 'Not authorized' })
    }

    return await listUIMessages(ctx, components.agent, {
      paginationOpts,
      threadId,
    })
  },
})
