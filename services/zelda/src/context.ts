import type { SessionManager } from './session/manager'
import type { ListenerTokenClaims } from './types'

export type AppDeps = {
  sessions: SessionManager
}

export type AppEnv = {
  Variables: {
    claims?: ListenerTokenClaims
    sessions: SessionManager
  }
}
