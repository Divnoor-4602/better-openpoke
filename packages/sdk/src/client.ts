import type { Client } from './generated/client';
import { createClient } from './generated/client';
import {
    connectIntegration,
    createThread,
    createThreadAgentRun,
    createThreadMessage,
    deleteThread,
    discardCalendarEvent,
    discardGmailDraft,
    disconnectIntegration,
    generateThreadTitle,
    listAgentRuns,
    listThreadAgentRuns,
    listThreadMessages,
    listThreads,
    retrieveAgentRun,
    retrieveIntegrationStatus,
    retrieveThread,
    retrieveTimezone,
    sendGmailDraft,
    setTimezone,
    streamAgentRunEvents,
    streamThreadMessage,
    updateCalendarEvent,
    updateGmailDraft,
    updateThread,
} from './generated/sdk.gen';
import type {
    AgentRunCreateRequest,
    AgentRunEventResource,
    AgentRunListResponse,
    AgentRunResource,
    AgentRunResponse,
    CalendarEventDiscardResponse,
    CalendarEventUpdateRequest,
    CalendarEventUpdateResponse,
    DeleteResponse,
    DraftDiscardResponse,
    DraftSendResponse,
    DraftUpdateRequest,
    DraftUpdateResponse,
    IntegrationConnectRequest,
    IntegrationConnectResponse,
    IntegrationDisconnectRequest,
    IntegrationDisconnectResponse,
    IntegrationStatusRequest,
    IntegrationStatusResponse,
    MessageCreateRequest,
    MessageCreateResponse,
    MessageListResponse,
    MessageStreamRequest,
    ThreadCreateResponse,
    ThreadListResponse,
    ThreadResponse,
    ThreadUpdateRequest,
    TimezoneResponse,
    TimezoneSetRequest,
} from './generated/types.gen';
import { createAuthedFetch, resolveBaseUrl } from './runtime';

export type OpenPokeClientOptions = {
  baseUrl?: string;
  fetch?: typeof globalThis.fetch;
};

export type PageQuery = {
  cursor?: string | null;
  limit?: number;
};

export type AgentRunEventsQuery = {
  afterId?: number;
};

export type EventStream = ReadableStream<Uint8Array> | null;
export type AgentLifecycleEventPayload = {
  runId: string;
  requestId?: string;
  threadId?: string | null;
  parentRunId?: string | null;
  scope: 'interaction' | 'execution';
  title?: string;
  memoryId?: string;
  parentMemoryId?: string | null;
  event: AgentRunEventResource;
};
export type AgentLifecycleStreamPart = {
  type: 'data-agent-event';
  data: AgentLifecycleEventPayload;
};
export type ExecutionLifecycleStreamPart = {
  type: 'data-execution-event';
  data: AgentLifecycleEventPayload;
};
export type UiMessageStreamPart =
  | AgentLifecycleStreamPart
  | ExecutionLifecycleStreamPart
  | { type: string; [key: string]: unknown };

type SdkResult<T> = Promise<{ data: T; request: Request; response: Response }>;
type StreamSdkResult = Promise<{ data: unknown; request: Request; response: Response }>;

export class ApiClient {
  readonly #client: Client;
  readonly #baseUrl: string;

  readonly threads = {
    agentRuns: {
      create: (threadId: string, body: AgentRunCreateRequest) => this.#createThreadAgentRun(threadId, body),
      list: (threadId: string, query?: PageQuery) => this.#listThreadAgentRuns(threadId, query),
    },
    create: () => this.#createThread(),
    delete: (threadId: string) => this.#deleteThread(threadId),
    list: (query?: PageQuery) => this.#listThreads(query),
    messages: {
      create: (threadId: string, body: MessageCreateRequest) => this.#createThreadMessage(threadId, body),
      list: (threadId: string, query?: PageQuery) => this.#listThreadMessages(threadId, query),
      stream: (threadId: string, body: MessageStreamRequest, signal?: AbortSignal) => this.#streamThreadMessage(threadId, body, signal),
      streamParts: (threadId: string, body: MessageStreamRequest) => this.#streamThreadMessageParts(threadId, body),
    },
    retrieve: (threadId: string) => this.#retrieveThread(threadId),
    generateTitle: (threadId: string) => this.#generateThreadTitle(threadId),
    update: (threadId: string, body: ThreadUpdateRequest) => this.#updateThread(threadId, body),
  };

  readonly agentRuns = {
    events: {
      stream: (requestId: string, query?: AgentRunEventsQuery) => this.#streamAgentRunEvents(requestId, query),
      streamParts: (requestId: string, query?: AgentRunEventsQuery) => this.#streamAgentRunEventParts(requestId, query),
    },
    list: (query?: PageQuery) => this.#listAgentRuns(query),
    retrieve: (requestId: string) => this.#retrieveAgentRun(requestId),
  };

  readonly integrations = {
    google: {
      connect: (body: IntegrationConnectRequest) => this.#connectGoogle(body),
      disconnect: (body: IntegrationDisconnectRequest) => this.#disconnectGoogle(body),
      status: (body: IntegrationStatusRequest) => this.#retrieveGoogleStatus(body),
    },
  };

  readonly gmail = {
    drafts: {
      discard: (input: { draftId: string }) => this.#discardGmailDraft(input.draftId),
      send: (input: { draftId: string }) => this.#sendGmailDraft(input.draftId),
      update: (input: { draftId: string } & DraftUpdateRequest) => {
        const { draftId, ...body } = input;
        return this.#updateGmailDraft(draftId, body);
      },
    },
  };

  readonly calendar = {
    events: {
      discard: (input: { eventId: string }) => this.#discardCalendarEvent(input.eventId),
      update: (input: { eventId: string } & CalendarEventUpdateRequest) => {
        const { eventId, ...body } = input;
        return this.#updateCalendarEvent(eventId, body);
      },
    },
  };

  readonly meta = {
    timezone: {
      retrieve: () => this.#retrieveTimezone(),
      set: (body: TimezoneSetRequest) => this.#setTimezone(body),
    },
  };

  constructor(options: OpenPokeClientOptions = {}) {
    this.#baseUrl = resolveBaseUrl(options.baseUrl);
    this.#client = createClient({
      baseUrl: this.#baseUrl,
      fetch: createAuthedFetch(options.fetch),
    });
  }

  #listThreads(query?: PageQuery): SdkResult<ThreadListResponse> {
    return listThreads({
      client: this.#client,
      query,
      throwOnError: true,
    });
  }

  #createThread(): SdkResult<ThreadCreateResponse> {
    return createThread({
      client: this.#client,
      throwOnError: true,
    });
  }

  #retrieveThread(threadId: string): SdkResult<ThreadResponse> {
    return retrieveThread({
      client: this.#client,
      path: { threadId },
      throwOnError: true,
    });
  }

  #updateThread(threadId: string, body: ThreadUpdateRequest): SdkResult<ThreadResponse> {
    return updateThread({
      body,
      client: this.#client,
      path: { threadId },
      throwOnError: true,
    });
  }

  #generateThreadTitle(threadId: string): SdkResult<ThreadResponse> {
    return generateThreadTitle({
      client: this.#client,
      path: { threadId },
      throwOnError: true,
    });
  }

  #deleteThread(threadId: string): SdkResult<DeleteResponse> {
    return deleteThread({
      client: this.#client,
      path: { threadId },
      throwOnError: true,
    });
  }

  #listThreadMessages(threadId: string, query?: PageQuery): SdkResult<MessageListResponse> {
    return listThreadMessages({
      client: this.#client,
      path: { threadId },
      query,
      throwOnError: true,
    });
  }

  #createThreadMessage(threadId: string, body: MessageCreateRequest): SdkResult<MessageCreateResponse> {
    return createThreadMessage({
      body,
      client: this.#client,
      path: { threadId },
      throwOnError: true,
    });
  }

  async #streamThreadMessage(
    threadId: string,
    body: MessageStreamRequest,
    signal?: AbortSignal,
  ): Promise<EventStream> {
    const result = (await streamThreadMessage({
      body,
      client: this.#client,
      parseAs: 'stream',
      path: { threadId },
      signal,
      throwOnError: true,
    })) as Awaited<StreamSdkResult>;

    return result.data as EventStream;
  }

  async #streamThreadMessageParts(threadId: string, body: MessageStreamRequest): Promise<AsyncIterable<UiMessageStreamPart>> {
    return streamUiMessageParts(await this.#streamThreadMessage(threadId, body));
  }

  #listThreadAgentRuns(threadId: string, query?: PageQuery): SdkResult<AgentRunListResponse> {
    return listThreadAgentRuns({
      client: this.#client,
      path: { threadId },
      query,
      throwOnError: true,
    });
  }

  #createThreadAgentRun(threadId: string, body: AgentRunCreateRequest): SdkResult<AgentRunResponse> {
    return createThreadAgentRun({
      body,
      client: this.#client,
      path: { threadId },
      throwOnError: true,
    });
  }

  #listAgentRuns(query?: PageQuery): SdkResult<AgentRunListResponse> {
    return listAgentRuns({
      client: this.#client,
      query,
      throwOnError: true,
    });
  }

  #retrieveAgentRun(requestId: string): SdkResult<AgentRunResponse> {
    return retrieveAgentRun({
      client: this.#client,
      path: { requestId },
      throwOnError: true,
    });
  }

  async #streamAgentRunEvents(requestId: string, query?: AgentRunEventsQuery): Promise<EventStream> {
    const result = (await streamAgentRunEvents({
      client: this.#client,
      parseAs: 'stream',
      path: { requestId },
      query,
      throwOnError: true,
    })) as Awaited<StreamSdkResult>;

    return result.data as EventStream;
  }

  async #streamAgentRunEventParts(requestId: string, query?: AgentRunEventsQuery): Promise<AsyncIterable<UiMessageStreamPart>> {
    return streamUiMessageParts(await this.#streamAgentRunEvents(requestId, query));
  }

  #connectGoogle(body: IntegrationConnectRequest): SdkResult<IntegrationConnectResponse> {
    return connectIntegration({
      body,
      client: this.#client,
      path: { provider: 'google' },
      throwOnError: true,
    });
  }

  #retrieveGoogleStatus(body: IntegrationStatusRequest): SdkResult<IntegrationStatusResponse> {
    return retrieveIntegrationStatus({
      body,
      client: this.#client,
      path: { provider: 'google' },
      throwOnError: true,
    });
  }

  #disconnectGoogle(body: IntegrationDisconnectRequest): SdkResult<IntegrationDisconnectResponse> {
    return disconnectIntegration({
      body,
      client: this.#client,
      path: { provider: 'google' },
      throwOnError: true,
    });
  }

  #sendGmailDraft(draftId: string): SdkResult<DraftSendResponse> {
    return sendGmailDraft({
      client: this.#client,
      path: { draft_id: draftId },
      throwOnError: true,
    });
  }

  #updateCalendarEvent(eventId: string, body: CalendarEventUpdateRequest): SdkResult<CalendarEventUpdateResponse> {
    return updateCalendarEvent({
      body,
      client: this.#client,
      path: { event_id: eventId },
      throwOnError: true,
    });
  }

  #discardCalendarEvent(eventId: string): SdkResult<CalendarEventDiscardResponse> {
    return discardCalendarEvent({
      client: this.#client,
      path: { event_id: eventId },
      throwOnError: true,
    });
  }

  #updateGmailDraft(draftId: string, body: DraftUpdateRequest): SdkResult<DraftUpdateResponse> {
    return updateGmailDraft({
      body,
      client: this.#client,
      path: { draft_id: draftId },
      throwOnError: true,
    });
  }

  #discardGmailDraft(draftId: string): SdkResult<DraftDiscardResponse> {
    return discardGmailDraft({
      client: this.#client,
      path: { draft_id: draftId },
      throwOnError: true,
    });
  }

  #retrieveTimezone(): SdkResult<TimezoneResponse> {
    return retrieveTimezone({
      client: this.#client,
      throwOnError: true,
    });
  }

  #setTimezone(body: TimezoneSetRequest): SdkResult<TimezoneResponse> {
    return setTimezone({
      body,
      client: this.#client,
      throwOnError: true,
    });
  }
}

export async function* streamUiMessageParts(stream: EventStream): AsyncIterable<UiMessageStreamPart> {
  if (!stream) return;
  const decoder = new TextDecoder();
  const reader = stream.getReader();
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const frames = buffer.split('\n\n');
      buffer = frames.pop() || '';
      for (const frame of frames) {
        const part = parseUiMessageStreamFrame(frame);
        if (part) yield part;
      }
    }
    buffer += decoder.decode();
    const part = parseUiMessageStreamFrame(buffer);
    if (part) yield part;
  } finally {
    reader.releaseLock();
  }
}

export function parseUiMessageStreamFrame(frame: string): UiMessageStreamPart | null {
  const data = frame
    .split(/\r?\n/)
    .filter(line => line.startsWith('data:'))
    .map(line => line.slice('data:'.length).trimStart())
    .join('\n')
    .trim();
  if (!data || data === '[DONE]') return null;
  return JSON.parse(data) as UiMessageStreamPart;
}

export const createOpenPokeClient = (options: OpenPokeClientOptions = {}) => new ApiClient(options);
export type { AgentRunEventResource, AgentRunResource };
