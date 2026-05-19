import type { UIMessage, UIMessageChunk } from 'ai';

import { DefaultChatTransport } from 'ai';

import type { ApiClient } from './client';
import type { MessageStreamRequest, UiMessage } from './generated/types.gen';

export type OpenPokeTransportOptions = {
  onThreadIdChange?: (threadId: null | string) => void;
  threadId?: string;
};

export class OpenPokeTransport extends DefaultChatTransport<UIMessage> {
  readonly #client: ApiClient;
  readonly #onThreadIdChange?: (threadId: null | string) => void;
  #threadId: null | string;

  constructor(client: ApiClient, options?: string | OpenPokeTransportOptions) {
    super();
    this.#client = client;
    if (typeof options === 'string') {
      this.#threadId = options;
      return;
    }
    this.#threadId = options?.threadId ?? null;
    this.#onThreadIdChange = options?.onThreadIdChange;
  }

  getThreadId(): null | string {
    return this.#threadId;
  }

  setThreadId(threadId: null | string): void {
    if (this.#threadId === threadId) return;
    this.#threadId = threadId;
    this.#onThreadIdChange?.(threadId);
  }

  async reconnectToStream(): Promise<null | ReadableStream<UIMessageChunk>> {
    return null;
  }

  async sendMessages(
    options: Parameters<DefaultChatTransport<UIMessage>['sendMessages']>[0],
  ): Promise<ReadableStream<UIMessageChunk>> {
    if (!this.#threadId) {
      const { data } = await this.#client.threads.create();
      this.setThreadId(data.thread.threadId);
    }
    const threadId = this.#threadId;
    if (!threadId) throw new Error('No thread id available');

    const stream = await this.#client.threads.messages.stream(
      threadId,
      {
        messages: options.messages as unknown as UiMessage[],
        timezone: getBrowserTimezone(),
        notifications: getNotificationPermission(),
      },
      options.abortSignal,
    );
    if (!stream) throw new Error('No stream returned from server');

    return this.processResponseStream(stream);
  }
}

function getBrowserTimezone(): MessageStreamRequest['timezone'] {
  try {
    return globalThis.Intl?.DateTimeFormat().resolvedOptions().timeZone || undefined;
  } catch {
    return undefined;
  }
}

function getNotificationPermission(): MessageStreamRequest['notifications'] {
  try {
    if (typeof Notification === 'undefined') return undefined;
    return Notification.permission as MessageStreamRequest['notifications'];
  } catch {
    return undefined;
  }
}
