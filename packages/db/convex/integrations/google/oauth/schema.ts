import { z } from 'zod'

export const GOOGLE_OAUTH_SCOPES = [
  'openid',
  'email',
  'https://www.googleapis.com/auth/calendar.readonly',
] as const

export const BuildAuthUrlInputSchema = z.object({
  state: z.string().min(1),
})
export type BuildAuthUrlInput = z.infer<typeof BuildAuthUrlInputSchema>

export const BuildAuthUrlOutputSchema = z.object({
  url: z.url(),
})
export type BuildAuthUrlOutput = z.infer<typeof BuildAuthUrlOutputSchema>

export const ExchangeCodeInputSchema = z.object({
  code: z.string().min(1),
})
export type ExchangeCodeInput = z.infer<typeof ExchangeCodeInputSchema>

export const GoogleTokenResponseSchema = z.object({
  access_token: z.string(),
  expires_in: z.number(),
  refresh_token: z.string(),
  scope: z.string(),
  token_type: z.string(),
})

export const ExchangeCodeOutputSchema = z.object({
  accessToken: z.string(),
  expiresIn: z.number(),
  refreshToken: z.string(),
  scope: z.string(),
  tokenType: z.string(),
})
export type ExchangeCodeOutput = z.infer<typeof ExchangeCodeOutputSchema>
