import type { WebhookEvent } from '@clerk/backend'

import { httpRouter } from 'convex/server'
import { Webhook } from 'svix'

import { internal } from './_generated/api'
import { httpAction } from './_generated/server'

const http = httpRouter()

http.route({
  handler: httpAction(async (ctx, request) => {
    const event = await validateRequest(request)
    if (!event) {
      return new Response('Error occurred', { status: 400 })
    }

    switch (event.type) {
      case 'user.created':
      case 'user.updated':
        await ctx.runMutation(
          internal.integrations.clerk.user.upsertFromClerk,
          {
            data: event.data,
          },
        )
        break

      case 'user.deleted': {
        const clerkUserId = event.data.id
        if (clerkUserId) {
          await ctx.runMutation(
            internal.integrations.clerk.user.deleteFromClerk,
            {
              clerkUserId,
            },
          )
        }
        break
      }

      default:
        console.log('Ignored Clerk webhook event', event.type)
    }

    return new Response(null, { status: 200 })
  }),
  method: 'POST',
  path: '/clerk-users-webhook',
})

async function validateRequest(req: Request): Promise<null | WebhookEvent> {
  const payloadString = await req.text()
  const svixHeaders = {
    'svix-id': req.headers.get('svix-id') ?? '',
    'svix-signature': req.headers.get('svix-signature') ?? '',
    'svix-timestamp': req.headers.get('svix-timestamp') ?? '',
  }
  const secret = process.env.CLERK_WEBHOOK_SECRET
  if (!secret) {
    console.error('Missing CLERK_WEBHOOK_SECRET')
    return null
  }
  const wh = new Webhook(secret)
  try {
    return wh.verify(payloadString, svixHeaders) as WebhookEvent
  } catch (error) {
    console.error('Error verifying webhook event', error)
    return null
  }
}

export default http
