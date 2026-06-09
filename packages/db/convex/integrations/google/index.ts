import { GoogleClient } from './client'

export const google = new GoogleClient()

export { GoogleClient } from './client'
export type {
  BuildAuthUrlInput,
  BuildAuthUrlOutput,
  ExchangeCodeInput,
  ExchangeCodeOutput,
} from './oauth/schema'
