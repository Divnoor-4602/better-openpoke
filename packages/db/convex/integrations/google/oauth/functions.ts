import type {
  BuildAuthUrlInput,
  BuildAuthUrlOutput,
  ExchangeCodeInput,
  ExchangeCodeOutput,
} from './schema'

import { validationError } from '../../../error'
import {
  BuildAuthUrlInputSchema,
  BuildAuthUrlOutputSchema,
  ExchangeCodeInputSchema,
  ExchangeCodeOutputSchema,
  GOOGLE_OAUTH_SCOPES,
  GoogleTokenResponseSchema,
} from './schema'

const AUTH_ENDPOINT = 'https://accounts.google.com/o/oauth2/v2/auth'
const TOKEN_ENDPOINT = 'https://oauth2.googleapis.com/token'

export function buildAuthUrl(input: BuildAuthUrlInput): BuildAuthUrlOutput {
  const args = BuildAuthUrlInputSchema.parse(input)
  const clientId = requireEnv('GOOGLE_OAUTH_CLIENT_ID')
  const redirectUri = requireEnv('GOOGLE_REDIRECT_URI')

  const params = new URLSearchParams({
    access_type: 'offline',
    client_id: clientId,
    include_granted_scopes: 'true',
    prompt: 'consent',
    redirect_uri: redirectUri,
    response_type: 'code',
    scope: GOOGLE_OAUTH_SCOPES.join(' '),
    state: args.state,
  })

  const parsed = BuildAuthUrlOutputSchema.safeParse({
    url: `${AUTH_ENDPOINT}?${params.toString()}`,
  })
  if (!parsed.success) {
    validationError({
      entity: 'GoogleOauth',
      message: `buildAuthUrl response invalid: ${parsed.error.message}`,
    })
  }
  return parsed.data
}

export async function exchangeCode(
  input: ExchangeCodeInput,
): Promise<ExchangeCodeOutput> {
  const args = ExchangeCodeInputSchema.parse(input)
  const clientId = requireEnv('GOOGLE_OAUTH_CLIENT_ID')
  const clientSecret = requireEnv('GOOGLE_OAUTH_CLIENT_SECRET')
  const redirectUri = requireEnv('GOOGLE_REDIRECT_URI')

  const body = new URLSearchParams({
    client_id: clientId,
    client_secret: clientSecret,
    code: args.code,
    grant_type: 'authorization_code',
    redirect_uri: redirectUri,
  })

  const res = await fetch(TOKEN_ENDPOINT, {
    body,
    headers: { 'content-type': 'application/x-www-form-urlencoded' },
    method: 'POST',
  })

  if (!res.ok) {
    const text = await res.text().catch(() => '')
    validationError({
      entity: 'GoogleOauth',
      message: `exchangeCode failed: ${res.status} ${text}`,
    })
  }

  const json = await res.json().catch(() => null)
  const tokenParsed = GoogleTokenResponseSchema.safeParse(json)
  if (!tokenParsed.success) {
    validationError({
      entity: 'GoogleOauth',
      message: `exchangeCode response invalid: ${tokenParsed.error.message}`,
    })
  }

  const parsed = ExchangeCodeOutputSchema.safeParse({
    accessToken: tokenParsed.data.access_token,
    expiresIn: tokenParsed.data.expires_in,
    refreshToken: tokenParsed.data.refresh_token,
    scope: tokenParsed.data.scope,
    tokenType: tokenParsed.data.token_type,
  })
  if (!parsed.success) {
    validationError({
      entity: 'GoogleOauth',
      message: `exchangeCode normalized response invalid: ${parsed.error.message}`,
    })
  }
  return parsed.data
}

function requireEnv(name: string): string {
  const value = process.env[name]
  if (!value) {
    validationError({ entity: 'GoogleOauth', message: `${name} is not set` })
  }
  return value
}
