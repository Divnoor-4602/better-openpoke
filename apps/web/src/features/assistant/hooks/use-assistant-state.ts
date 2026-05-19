import type { AssistantState, ChatStatus } from '../lib/agent-state'
import type { OpenPokeChatMessage } from '../types'

import { deriveAssistantState } from '../lib/agent-state'

export type { AssistantState }

export function useAssistantState(
  status: ChatStatus,
  messages: OpenPokeChatMessage[],
  halted = false,
): AssistantState {
  return deriveAssistantState(status, messages, halted)
}
