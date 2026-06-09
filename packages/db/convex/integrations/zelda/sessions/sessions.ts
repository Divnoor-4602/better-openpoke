import type { ZeldaClient } from '../client'
import type {
  GetSessionByIdInput,
  GetSessionByIdOutput,
  TerminateSessionInput,
  TerminateSessionOutput,
} from './schema'

import { getSessionById, terminateSession } from './functions'

export class Sessions {
  constructor(private readonly client: ZeldaClient) {}

  getById(input: GetSessionByIdInput): Promise<GetSessionByIdOutput> {
    return getSessionById(this.client, input)
  }

  terminate(input: TerminateSessionInput): Promise<TerminateSessionOutput> {
    return terminateSession(this.client, input)
  }
}
