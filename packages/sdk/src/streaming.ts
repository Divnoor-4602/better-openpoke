/**
 * Types and Zod schemas for the AI SDK UI message stream parts
 * emitted by the server's data-agent-event SSE chunks.
 *
 * These are not generated from the OpenAPI spec because they are
 * streaming-only constructs, not REST resources.
 */

import { z } from 'zod';

import { zAgentRunEventResource, zAgentRunResource } from './generated/zod.gen';

/**
 * The payload of a `data-agent-event` SSE chunk. It is a run envelope with
 * a single `event` instead of the `parts[]` array found in the REST resource.
 */
export const zAgentEventStreamPayload = zAgentRunResource
  .omit({ createdAt: true, ok: true, parts: true, status: true, updatedAt: true })
  .extend({ event: zAgentRunEventResource });

export type AgentEventStreamPayload = z.infer<typeof zAgentEventStreamPayload>;

/**
 * The UIDataTypes map for `useChat`. Pass `zAgentEventStreamPayload` as the
 * schema so that `data-agent-event` parts surface in `message.parts[]`.
 *
 * @example
 * ```tsx
 * const { messages } = useChat<AgentChatMessage>({
 *   dataPartSchemas: openPokeDataPartSchemas,
 *   transport,
 * });
 * ```
 */
export const openPokeDataPartSchemas = {
  'agent-event': zAgentEventStreamPayload,
} as const;

export type OpenPokeUIDataTypes = {
  'agent-event': AgentEventStreamPayload;
};
