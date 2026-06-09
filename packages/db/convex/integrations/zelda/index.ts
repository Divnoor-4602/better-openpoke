import { ZeldaClient } from './client'

export const zelda = new ZeldaClient()

export { ZeldaClient } from './client'

export type {
  GetSessionByIdInput,
  GetSessionByIdOutput,
  SessionState,
  TerminateSessionInput,
  TerminateSessionOutput,
} from './sessions/schema'
