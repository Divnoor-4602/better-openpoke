import type { Client } from './generated/client';
import { createClient } from './generated/client';
import {
    connectIntegration,
    createThread,
    createThreadAgentRun,
    createThreadMessage,
    deleteThread,
    disconnectIntegration,
    listAgentRuns,
    listThreadAgentRuns,
    listThreadMessages,
    listThreads,
    retrieveAgentRun,
    retrieveIntegrationStatus,
    retrieveThread,
    streamAgentRunEvents,
    streamThreadMessage,
    updateThread,
} from './generated/sdk.gen';
import type {
    AgentRunCreateRequest,
    AgentRunListResponse,
    AgentRunResponse,
    DeleteResponse,
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
} from './generated/types.gen';
import { DEFAULT_OPENPOKE_BASE_URL } from './runtime';

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

type SdkResult<T> = Promise<{ data: T; request: Request; response: Response }>;
type StreamSdkResult = Promise<{ data: unknown; request: Request; response: Response }>;

export class ApiClient {
  readonly #client: Client;

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
      stream: (threadId: string, body: MessageStreamRequest) => this.#streamThreadMessage(threadId, body),
    },
    retrieve: (threadId: string) => this.#retrieveThread(threadId),
    update: (threadId: string, body: ThreadUpdateRequest) => this.#updateThread(threadId, body),
  };

  readonly agentRuns = {
    events: {
      stream: (requestId: string, query?: AgentRunEventsQuery) => this.#streamAgentRunEvents(requestId, query),
    },
    list: (query?: PageQuery) => this.#listAgentRuns(query),
    retrieve: (requestId: string) => this.#retrieveAgentRun(requestId),
  };

  readonly integrations = {
    gmail: {
      connect: (body: IntegrationConnectRequest) => this.#connectGmail(body),
      disconnect: (body: IntegrationDisconnectRequest) => this.#disconnectGmail(body),
      status: (body: IntegrationStatusRequest) => this.#retrieveGmailStatus(body),
    },
  };

  constructor(options: OpenPokeClientOptions = {}) {
    this.#client = createClient({
      baseUrl: options.baseUrl ?? DEFAULT_OPENPOKE_BASE_URL,
      fetch: options.fetch,
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

  async #streamThreadMessage(threadId: string, body: MessageStreamRequest): Promise<EventStream> {
    const result = (await streamThreadMessage({
      body,
      client: this.#client,
      parseAs: 'stream',
      path: { threadId },
      throwOnError: true,
    })) as Awaited<StreamSdkResult>;

    return result.data as EventStream;
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

  #connectGmail(body: IntegrationConnectRequest): SdkResult<IntegrationConnectResponse> {
    return connectIntegration({
      body,
      client: this.#client,
      path: { provider: 'gmail' },
      throwOnError: true,
    });
  }

  #retrieveGmailStatus(body: IntegrationStatusRequest): SdkResult<IntegrationStatusResponse> {
    return retrieveIntegrationStatus({
      body,
      client: this.#client,
      path: { provider: 'gmail' },
      throwOnError: true,
    });
  }

  #disconnectGmail(body: IntegrationDisconnectRequest): SdkResult<IntegrationDisconnectResponse> {
    return disconnectIntegration({
      body,
      client: this.#client,
      path: { provider: 'gmail' },
      throwOnError: true,
    });
  }
}

export const createOpenPokeClient = (options: OpenPokeClientOptions = {}) => new ApiClient(options);
