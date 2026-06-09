import type { AuthConfig } from 'convex/server'

export default {
  providers: [
    {
      applicationID: 'convex',
      domain: process.env.CLERK_JWT_ISSUER_DOMAIN!,
    },
  ],
} satisfies AuthConfig
