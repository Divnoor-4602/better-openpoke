import type { AgentEventStreamPayload } from '@openpoke/sdk'
import type { UIMessage } from 'ai'

import { getToolName, isReasoningUIPart, isTextUIPart, isToolUIPart } from 'ai'

import type { CatalogPlacement } from '../components/catalog/types'
import type { OpenPokeChatMessage } from '../types'

import { findGoogleNotConnectedTrigger } from '../components/catalog/components/integrations/utils'
import {
  CATALOG_TOOL_NAMES,
  getCatalogEntry,
} from '../components/catalog/registry'

export type AssistantState =
  | { label: string; toolCallId: string; toolName: string; type: 'active' }
  | { type: 'error' }
  | { type: 'halted' }
  | { type: 'idle' }
  | { type: 'ready' }
  | { type: 'thinking' }
  | { type: 'typing' }

export type ChatStatus = 'error' | 'idle' | 'ready' | 'streaming' | 'submitted'

export type NormalizedToolCall = {
  completedAt?: number
  error?: string
  input?: unknown
  order: number
  output?: unknown
  source: ToolCallSource
  startedAt?: number
  state: ToolCallState
  toolCallId: string
  toolName: string
}

export type ToolCallSource = 'execution' | 'interaction'

export type ToolCallState = 'cancel' | 'error' | 'running' | 'start' | 'success'

export const HIDDEN_TOOL_NAMES: ReadonlySet<string> = new Set([
  'send_message_to_agent',
  'send_message_to_user',
  'send_messages_to_agents',
  'wait',
])

export const ACTIVE_TOOL_LABELS = [
  'Razzmatazzing',
  'Jorking',
  'UGAHHHHH',
  'In-progress',
] as const

const NON_TOOL_EVENT_TYPES: ReadonlySet<string> = new Set([
  'execution.submitted',
  'model.completed',
  'model.reasoning.delta',
  'model.started',
  'model.text.delta',
  'run.completed',
  'run.created',
  'run.failed',
  'run.started',
])

const TOOL_EVENT_TYPES = {
  inputAvailable: 'tool.input.available',
  inputDelta: 'tool.input.delta',
  inputStarted: 'tool.input.started',
  outputAvailable: 'tool.output.available',
  outputError: 'tool.output.error',
} as const

type AgentEventPart = {
  data: AgentEventStreamPayload
  type: 'data-agent-event'
}

type PartialCall = {
  completedAt?: number
  error?: string
  input?: unknown
  output?: unknown
  source: ToolCallSource
  startedAt?: number
  state: ToolCallState
  toolCallId: string
  toolName: string
}

const parseTimestamp = (value: unknown): number | undefined => {
  if (typeof value !== 'string' || !value) return undefined
  const ms = Date.parse(value)
  return Number.isNaN(ms) ? undefined : ms
}

function fromAgentEventPart(part: AgentEventPart): null | PartialCall {
  const event = part.data.event
  const eventType = event.type
  if (NON_TOOL_EVENT_TYPES.has(eventType)) return null
  if (!eventType.startsWith('tool.')) return null

  const toolName = event.toolName ?? ''
  if (!toolName) return null
  const toolCallId =
    event.toolCallId ?? `${toolName}:${event.runId}:${event.sequence}`

  let state: ToolCallState
  switch (eventType) {
    case TOOL_EVENT_TYPES.inputAvailable:
      state = 'running'
      break
    case TOOL_EVENT_TYPES.inputDelta:
    case TOOL_EVENT_TYPES.inputStarted:
      state = 'start'
      break
    case TOOL_EVENT_TYPES.outputAvailable:
      state = 'success'
      break
    case TOOL_EVENT_TYPES.outputError:
      state = 'error'
      break
    default:
      state = 'running'
  }

  const createdAt = parseTimestamp((event as { createdAt?: unknown }).createdAt)
  const isStartEvent =
    eventType === TOOL_EVENT_TYPES.inputStarted ||
    eventType === TOOL_EVENT_TYPES.inputDelta ||
    eventType === TOOL_EVENT_TYPES.inputAvailable
  const isEndEvent =
    eventType === TOOL_EVENT_TYPES.outputAvailable ||
    eventType === TOOL_EVENT_TYPES.outputError

  return {
    completedAt: isEndEvent ? createdAt : undefined,
    error: event.error ?? undefined,
    input: event.input ?? undefined,
    output: event.output ?? undefined,
    source: part.data.scope === 'interaction' ? 'interaction' : 'execution',
    startedAt: isStartEvent ? createdAt : undefined,
    state,
    toolCallId,
    toolName,
  }
}

function fromToolUIPart(part: UIMessage['parts'][number]): null | PartialCall {
  if (!isToolUIPart(part)) return null
  const toolName = getToolName(part)
  const toolCallId = (part as { toolCallId?: string }).toolCallId ?? toolName
  const partState = (part as { state?: string }).state

  let state: ToolCallState
  switch (partState) {
    case 'approval-requested':
    case 'approval-responded':
    case 'input-available':
      state = 'running'
      break
    case 'input-streaming':
      state = 'start'
      break
    case 'output-available':
      state = 'success'
      break
    case 'output-error':
      state = 'error'
      break
    default:
      state = 'start'
  }

  return {
    error: (part as { errorText?: string }).errorText,
    input: (part as { input?: unknown }).input,
    output: (part as { output?: unknown }).output,
    source: 'interaction',
    state,
    toolCallId,
    toolName,
  }
}

function isAgentEventPart(part: unknown): part is AgentEventPart {
  return (
    typeof part === 'object' &&
    part !== null &&
    (part as { type?: unknown }).type === 'data-agent-event'
  )
}

const STATE_ORDER: Record<ToolCallState, number> = {
  cancel: 2,
  error: 2,
  running: 1,
  start: 0,
  success: 2,
}

export function deriveAssistantState(
  status: ChatStatus,
  messages: OpenPokeChatMessage[],
  halted = false,
): AssistantState {
  if (status === 'error') return { type: 'error' }
  if (status === 'idle') return { type: 'idle' }
  if (status === 'ready') return halted ? { type: 'halted' } : { type: 'ready' }
  if (status === 'submitted') return { type: 'thinking' }

  const last = messages.findLast((m) => m.role === 'assistant')
  if (!last) return { type: 'thinking' }
  const parts = last.parts

  if (parts.some(isReasoningUIPart)) return { type: 'thinking' }

  const active = getActiveToolCall(messages)
  if (active) {
    return {
      label: pickActiveLabel(last.id),
      toolCallId: active.toolCallId,
      toolName: active.toolName,
      type: 'active',
    }
  }

  if (parts.some(isTextUIPart)) return { type: 'typing' }
  return { type: 'thinking' }
}

const ACTIVE_TOOL_SCAN_DEPTH = 5

export type CatalogVariant =
  | { call: NormalizedToolCall; kind: 'tool' }
  | { kind: 'integrations-button'; message?: string }

export type MessageBlock =
  | {
      id: string
      placement: CatalogPlacement
      type: 'catalog'
      variant: CatalogVariant
    }
  | { calls: NormalizedToolCall[]; id: string; type: 'tools' }
  | { id: string; text: string; type: 'text' }


export function buildMessageBlocks(
  message: OpenPokeChatMessage,
  options: { suppressIntegrationsButton?: boolean } = {},
): MessageBlock[] {
  const parts = message.parts ?? []
  const callsById = new Map<string, NormalizedToolCall>()
  for (const call of getNormalizedToolCalls(message)) {
    callsById.set(call.toolCallId, call)
  }
  const placed = new Set<string>()
  const blocks: MessageBlock[] = []

  const pushText = (text: string, index: number) => {
    if (!text) return
    const last = blocks[blocks.length - 1]
    if (last && last.type === 'text') last.text += text
    else blocks.push({ id: `text:${index}`, text, type: 'text' })
  }

  const pushTool = (call: NormalizedToolCall) => {
    const last = blocks[blocks.length - 1]
    if (last && last.type === 'tools') last.calls.push(call)
    else
      blocks.push({
        calls: [call],
        id: `tools:${call.toolCallId}`,
        type: 'tools',
      })
  }

  parts.forEach((part, index) => {
    if (isTextUIPart(part)) {
      pushText(part.text, index)
      return
    }
    const partial = isAgentEventPart(part)
      ? fromAgentEventPart(part)
      : fromToolUIPart(part)
    if (!partial) return
    if (HIDDEN_TOOL_NAMES.has(partial.toolName)) return
    const call = callsById.get(partial.toolCallId)
    if (!call) return
    if (call.order !== index) return
    if (placed.has(call.toolCallId)) return
    placed.add(call.toolCallId)
    if (CATALOG_TOOL_NAMES.has(call.toolName)) {
      const entry = getCatalogEntry(call.toolName)
      if (entry) {
        blocks.push({
          id: `catalog:${call.toolCallId}`,
          placement: entry.placement,
          type: 'catalog',
          variant: { call, kind: 'tool' },
        })
        return
      }
    }
    pushTool(call)
  })

  const augmented: MessageBlock[] = [...blocks]
  // Hold the button until streaming settles. If we surface it mid-stream the
  // user sees it appear, then the later assistant text streams in and pushes
  // it down — visually jumpy. The caller passes `suppressIntegrationsButton`
  // while the assistant is still in flight.
  if (!options.suppressIntegrationsButton) {
    const trigger = findGoogleNotConnectedTrigger(message)
    if (trigger) {
      augmented.push({
        id: `catalog:integrations-button:${trigger.toolCallId}`,
        placement: 'block',
        type: 'catalog',
        variant: { kind: 'integrations-button' },
      })
    }
  }

  return augmented
}

export function getActiveToolCall(
  messages: OpenPokeChatMessage[],
): NormalizedToolCall | null {
  const assistants = messages.filter((m) => m.role === 'assistant')
  const recent = assistants.slice(-ACTIVE_TOOL_SCAN_DEPTH)
  for (let i = recent.length - 1; i >= 0; i--) {
    const message = recent[i]
    if (!message) continue
    const inFlight =
      getNormalizedToolCalls(message).findLast(isToolCallInFlight)
    if (inFlight) return inFlight
  }
  return null
}

export function getAssistantText(message: OpenPokeChatMessage): string {
  const parts = message.parts ?? []
  return parts
    .filter(isTextUIPart)
    .map((part) => part.text)
    .join('')
}

export function getNormalizedToolCalls(
  message: OpenPokeChatMessage,
  options: { includeHidden?: boolean } = {},
): NormalizedToolCall[] {
  const parts = message.parts ?? []
  const byId = new Map<string, NormalizedToolCall>()

  parts.forEach((part, index) => {
    const partial = isAgentEventPart(part)
      ? fromAgentEventPart(part)
      : fromToolUIPart(part)
    if (!partial) return
    if (!options.includeHidden && HIDDEN_TOOL_NAMES.has(partial.toolName))
      return

    const existing = byId.get(partial.toolCallId)
    if (!existing) {
      byId.set(partial.toolCallId, { ...partial, order: index })
      return
    }
    byId.set(partial.toolCallId, {
      ...existing,
      completedAt: pickLatest(existing.completedAt, partial.completedAt),
      error: partial.error ?? existing.error,
      input: partial.input ?? existing.input,
      output: partial.output ?? existing.output,
      startedAt: pickEarliest(existing.startedAt, partial.startedAt),
      state: pickLaterState(existing.state, partial.state),
    })
  })

  return Array.from(byId.values()).sort((a, b) => a.order - b.order)
}

// Earliest start + latest completion across a list of tool calls.
export function getRunSpan(calls: NormalizedToolCall[]): {
  completedAt?: number
  startedAt?: number
} {
  let startedAt: number | undefined
  let completedAt: number | undefined
  for (const c of calls) {
    if (
      c.startedAt !== undefined &&
      (startedAt === undefined || c.startedAt < startedAt)
    ) {
      startedAt = c.startedAt
    }
    if (
      c.completedAt !== undefined &&
      (completedAt === undefined || c.completedAt > completedAt)
    ) {
      completedAt = c.completedAt
    }
  }
  return { completedAt, startedAt }
}

export function isStreaming(status: ChatStatus): boolean {
  return status === 'streaming' || status === 'submitted'
}

export function isToolCallInFlight(call: NormalizedToolCall): boolean {
  return call.state === 'start' || call.state === 'running'
}

function pickActiveLabel(seed: string): string {
  let hash = 0
  for (let i = 0; i < seed.length; i++) {
    hash = (hash * 31 + seed.charCodeAt(i)) | 0
  }
  const index = Math.abs(hash) % ACTIVE_TOOL_LABELS.length
  return ACTIVE_TOOL_LABELS[index] ?? 'In-progress'
}

function pickEarliest(a: number | undefined, b: number | undefined) {
  if (a === undefined) return b
  if (b === undefined) return a
  return Math.min(a, b)
}

function pickLaterState(a: ToolCallState, b: ToolCallState): ToolCallState {
  return STATE_ORDER[b] >= STATE_ORDER[a] ? b : a
}

function pickLatest(a: number | undefined, b: number | undefined) {
  if (a === undefined) return b
  if (b === undefined) return a
  return Math.max(a, b)
}
