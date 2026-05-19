import type { NormalizedToolCall } from './agent-state'
import type { ToolCategory } from './tool-registry'

import { getRunSpan, isToolCallInFlight } from './agent-state'
import { getActiveBrandCategories } from './tool-registry'

export type ToolsSummary = {
  categories: ToolCategory[]
  completedAt?: number
  isRunning: boolean
  startedAt?: number
}

// Single-pass derivation of every value the tools UI needs from a list of calls.
export const summarizeTools = (calls: NormalizedToolCall[]): ToolsSummary => {
  const { completedAt, startedAt } = getRunSpan(calls)
  return {
    categories: getActiveBrandCategories(calls),
    completedAt,
    isRunning: calls.some(isToolCallInFlight),
    startedAt,
  }
}
