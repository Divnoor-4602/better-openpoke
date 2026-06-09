import type {
  BuildAuthUrlInput,
  BuildAuthUrlOutput,
  ExchangeCodeInput,
  ExchangeCodeOutput,
} from './schema'

import { buildAuthUrl, exchangeCode } from './functions'

export class Oauth {
  buildAuthUrl(input: BuildAuthUrlInput): BuildAuthUrlOutput {
    return buildAuthUrl(input)
  }

  exchangeCode(input: ExchangeCodeInput): Promise<ExchangeCodeOutput> {
    return exchangeCode(input)
  }
}
