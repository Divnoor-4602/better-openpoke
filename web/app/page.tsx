'use client';

import { useChat } from '@ai-sdk/react';
import { DefaultChatTransport } from 'ai';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import SettingsModal, { useSettings } from '@/components/SettingsModal';
import { ChatHeader } from '@/components/chat/ChatHeader';
import { ChatInput } from '@/components/chat/ChatInput';
import { ChatMessages } from '@/components/chat/ChatMessages';
import { ErrorBanner } from '@/components/chat/ErrorBanner';
import { useAutoScroll } from '@/components/chat/useAutoScroll';
import type { ChatBubble } from '@/components/chat/types';

const POLL_INTERVAL_MS = 2500;

type ExecutionPart = {
  id?: number | null;
  runId?: string;
  sequence?: number;
  type?: string;
  state?: string | null;
  toolName?: string | null;
  toolCallId?: string | null;
  text?: string | null;
  input?: unknown;
  output?: unknown;
  error?: string | null;
  createdAt?: string | null;
};

type ExecutionRun = {
  runId?: string;
  requestId?: string;
  memoryId?: string;
  scope?: 'interaction' | 'execution';
  parentMemoryId?: string | null;
  title?: string;
  status?: string;
  ok?: boolean | null;
  updatedAt?: string;
  parts?: ExecutionPart[];
};

const textFromParts = (parts: any[]): string =>
  parts
    .filter(part => part?.type === 'text')
    .map(part => part.text || '')
    .join('');

const toolNameFromPart = (part: any): string => {
  const typeName = typeof part?.type === 'string' && part.type.startsWith('tool-')
    ? part.type.slice('tool-'.length)
    : '';
  const rawName = part?.toolName || part?.tool_name || typeName || part?.toolCallId || part?.tool_call_id || 'Tool';
  return String(rawName)
    .replace(/^tool-/, '')
    .replace(/_/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/\b\w/g, char => char.toUpperCase());
};

const statusLinesFromParts = (parts: any[]): string[] => {
  const lines: string[] = [];
  const seen = new Set<string>();

  const add = (line: string) => {
    if (!line || seen.has(line)) return;
    seen.add(line);
    lines.push(line);
  };

  for (const part of parts) {
    const isToolPart = typeof part?.type === 'string' && part.type.startsWith('tool-');
    const isToolComplete =
      part?.type === 'tool-output-available' ||
      (isToolPart && part?.state === 'output-available' && part?.preliminary !== true);
    const isToolFailed =
      part?.type === 'tool-output-error' ||
      (isToolPart && part?.state === 'output-error');
    const isToolLoading =
      part?.type === 'tool-input-start' ||
      part?.type === 'tool-input-delta' ||
      part?.type === 'tool-input-available' ||
      (isToolPart && ['input-streaming', 'input-available'].includes(part?.state || ''));

    if (isToolComplete) {
      add(`${toolNameFromPart(part)} complete`);
      continue;
    }
    if (isToolFailed) {
      add(`${toolNameFromPart(part)} failed`);
      continue;
    }
    if (isToolLoading) {
      add(`Loading - ${toolNameFromPart(part)}`);
      continue;
    }
    if (part?.type !== 'data-agent-event' && part?.type !== 'data-execution-event') continue;
    const payload = part.data || {};
    const event = payload.event || {};
    const taskTitle = payload.title || payload.memoryId || 'Task';
    if ((event.type === 'status' || event.type === 'execution.submitted') && event.state === 'queued') {
      add(`Waiting - ${taskTitle}`);
    } else if ((event.type === 'status' || event.type === 'run.started') && event.state === 'running') {
      add(`Working - ${taskTitle}`);
    } else if ((event.type === 'tool-call' || event.type === 'tool.input.available') && event.state === 'input-available') {
      add(`Loading - ${toolNameFromPart({ ...event, type: `tool-${event.toolName || 'tool'}` })}`);
    } else if ((event.type === 'tool-result' || event.type === 'tool.output.available') && event.state === 'output-available') {
      add(`${toolNameFromPart({ ...event, type: `tool-${event.toolName || 'tool'}` })} complete`);
    } else if ((event.type === 'tool-result' || event.type === 'tool.output.error') && event.state === 'output-error') {
      add(`${toolNameFromPart({ ...event, type: `tool-${event.toolName || 'tool'}` })} failed`);
    } else if ((event.type === 'status' || event.type === 'run.completed') && event.state === 'completed') {
      add(`${taskTitle} complete`);
    } else if ((event.type === 'status' || event.type === 'run.failed') && event.state === 'failed') {
      add(`${taskTitle} failed`);
    }
  }

  return lines;
};

const streamEventsToRuns = (messages: any[]): ExecutionRun[] => {
  const byId = new Map<string, ExecutionRun>();
  for (const message of messages) {
    for (const part of message?.parts || []) {
      if (part?.type !== 'data-agent-event' && part?.type !== 'data-execution-event') continue;
      const payload = part.data || {};
      const event = payload.event || {};
      if (payload.scope === 'interaction') continue;
      const requestId = payload.requestId || payload.runId || payload.request_id;
      if (!requestId) continue;
      const run: ExecutionRun = byId.get(requestId) || {
        runId: payload.runId || requestId,
        requestId,
        memoryId: payload.memoryId,
        parentMemoryId: payload.parentMemoryId,
        scope: payload.scope || 'execution',
        title: payload.title || payload.memoryId,
        status: 'running',
        parts: [],
      };
      run.runId = payload.runId || run.runId;
      run.memoryId = payload.memoryId || run.memoryId;
      run.scope = payload.scope || run.scope;
      run.parentMemoryId = payload.parentMemoryId || run.parentMemoryId;
      if ((event.type === 'status' || event.type?.startsWith?.('run.')) && event.state) run.status = event.state;
      if (event.state === 'completed') run.ok = true;
      if (event.state === 'failed' || event.state === 'output-error') run.ok = false;
      run.parts = [...(run.parts || []), event];
      byId.set(requestId, run);
    }
  }
  return Array.from(byId.values()).reverse();
};

const mergeExecutionRuns = (storedRuns: ExecutionRun[], streamedRuns: ExecutionRun[]): ExecutionRun[] => {
  const byId = new Map<string, ExecutionRun>();
  for (const run of [...storedRuns, ...streamedRuns]) {
    const requestId = run.requestId;
    if (!requestId) continue;
    const existing = byId.get(requestId);
    if (!existing) {
      byId.set(requestId, { ...run, parts: dedupeParts(run.parts || []) });
      continue;
    }
    byId.set(requestId, {
      ...existing,
      ...run,
      parts: dedupeParts([...(existing.parts || []), ...(run.parts || [])]),
    });
  }
  return Array.from(byId.values()).sort((a, b) => String(b.updatedAt || '').localeCompare(String(a.updatedAt || '')));
};

const dedupeParts = (parts: ExecutionPart[]): ExecutionPart[] => {
  const seen = new Set<string>();
  return parts.filter((part, index) => {
    const key =
      part.id != null
        ? `id:${part.id}`
        : part.runId && part.sequence != null
          ? `${part.runId}:${part.sequence}`
          : `${part.createdAt || ''}:${part.type || ''}:${index}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
};

const toBubbles = (messages: any[]): ChatBubble[] =>
  messages
    .map((message: any) => {
      const parts = Array.isArray(message.parts) ? message.parts : [];
      const text = message.role === 'assistant'
        ? textFromParts(parts)
        : parts.length > 0
          ? textFromParts(parts)
          : message.content || '';
      const statusLines = message.role === 'assistant'
        ? [...(message.metadata?.statusLines || []), ...statusLinesFromParts(parts)]
        : undefined;
      return {
        id: message.id,
        role: message.role,
        text,
        statusLines,
      };
    })
    .filter((message: ChatBubble) => (
      message.text.trim().length > 0 ||
      (message.role === 'assistant' && (message.statusLines?.length || 0) > 0)
    ));

const hasAssistantTextAfterLastUser = (messages: any[]): boolean => {
  const lastUserIndex = messages.reduce(
    (lastIndex, message, index) => (message?.role === 'user' ? index : lastIndex),
    -1,
  );
  return messages
    .slice(lastUserIndex + 1)
    .some((message: any) => message?.role === 'assistant' && textFromParts(message?.parts || []).trim().length > 0);
};

export default function Page() {
  const { settings, setSettings } = useSettings();
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState('');
  const [executionRuns, setExecutionRuns] = useState<ExecutionRun[]>([]);
  const [error, setError] = useState<string | null>(null);
  const streamedRunSourcesRef = useRef<Map<string, EventSource>>(new Map());
  const streamedRunTextRef = useRef<Map<string, string>>(new Map());
  const executionMessageIdsRef = useRef<Set<string>>(new Set());
  const knownExecutionRunIdsRef = useRef<Set<string>>(new Set());
  const hasLoadedExecutionRunsRef = useRef(false);
  const chat = useChat({
    transport: new DefaultChatTransport({ api: '/api/chat/stream' }),
    onError: (err: Error) => setError(err.message),
  } as any);

  const chatBubbles = useMemo(() => toBubbles(chat.messages || []), [chat.messages]);
  const messages = chatBubbles;
  const streamedRuns = useMemo(() => streamEventsToRuns(chat.messages || []), [chat.messages]);
  const visibleRuns = useMemo(() => mergeExecutionRuns(executionRuns, streamedRuns), [executionRuns, streamedRuns]);
  const isInteractionTurnActive = chat.status === 'submitted' || chat.status === 'streaming';
  const isWaitingForResponse =
    chat.status === 'submitted' ||
    (chat.status === 'streaming' && !hasAssistantTextAfterLastUser(chat.messages || []));
  const canSubmitMessage = input.trim().length > 0 && !isInteractionTurnActive;
  const { scrollContainerRef, handleScroll } = useAutoScroll({
    items: messages,
    isWaiting: isWaitingForResponse,
  });

  const openSettings = useCallback(() => setOpen(true), []);
  const closeSettings = useCallback(() => setOpen(false), []);

  const appendExecutionMessage = useCallback((requestId: string, rawText: string, statusLine?: string) => {
    const text = rawText.trim();
    if (!text) return;
    const messageId = `execution-${requestId}`;
    if (executionMessageIdsRef.current.has(messageId)) return;
    executionMessageIdsRef.current.add(messageId);
    (chat as any).setMessages((prev: any[]) => [
      ...(Array.isArray(prev) ? prev : []),
      {
        id: messageId,
        role: 'assistant',
        parts: [{ type: 'text', text }],
        metadata: {
          requestId,
          statusLines: statusLine ? [statusLine] : ['Task complete'],
        },
      },
    ]);
  }, [chat]);

  const loadExecutionRuns = useCallback(async () => {
    try {
      const res = await fetch('/api/execution/agents', { cache: 'no-store' });
      if (!res.ok) return;
      const data = await res.json();
      if (Array.isArray(data?.runs)) {
        setExecutionRuns(data.runs);
        if (!hasLoadedExecutionRunsRef.current) {
          for (const run of data.runs) {
            if (run?.requestId) {
              knownExecutionRunIdsRef.current.add(run.requestId);
              if (run.status === 'completed' || run.status === 'failed') {
                executionMessageIdsRef.current.add(`execution-${run.requestId}`);
              }
            }
          }
          hasLoadedExecutionRunsRef.current = true;
        }
        for (const run of data.runs) {
          if (run?.requestId) knownExecutionRunIdsRef.current.add(run.requestId);
        }
      }
    } catch (err: any) {
      if (err?.name !== 'AbortError') console.error('Failed to load execution runs', err);
    }
  }, []);

  const applyExecutionEvent = useCallback((payload: any) => {
    if (payload?.scope === 'interaction') return;
    const requestId = payload?.requestId || payload?.runId;
    const event = payload?.event || {};
    if (!requestId) return;

    setExecutionRuns(prev => {
      const existing = prev.find(run => run.requestId === requestId);
      const nextRun: ExecutionRun = {
        ...(existing || {}),
        runId: payload.runId || existing?.runId || requestId,
        requestId,
        memoryId: payload.memoryId || existing?.memoryId,
        scope: payload.scope || existing?.scope || 'execution',
        parentMemoryId: payload.parentMemoryId || existing?.parentMemoryId,
        title: payload.title || existing?.title || payload.memoryId,
        status:
          (event.type === 'status' || event.type?.startsWith?.('run.')) && event.state
            ? event.state
            : existing?.status || 'running',
        ok:
          event.state === 'completed'
            ? true
            : event.state === 'failed' || event.state === 'output-error'
              ? false
              : existing?.ok,
        parts: dedupeParts([...(existing?.parts || []), event]),
      };
      return [nextRun, ...prev.filter(run => run.requestId !== requestId)];
    });

  }, []);

  useEffect(() => {
    void loadExecutionRuns();
    const intervalId = window.setInterval(() => void loadExecutionRuns(), POLL_INTERVAL_MS);
    return () => window.clearInterval(intervalId);
  }, [loadExecutionRuns]);

  useEffect(() => {
    const activeRequestIds = new Set(
      visibleRuns
        .filter(
          run =>
            run.requestId &&
            (!['completed', 'failed'].includes(run.status || '') ||
              !executionMessageIdsRef.current.has(`execution-${run.requestId}`)),
        )
        .map(run => run.requestId as string),
    );

    for (const [requestId, source] of streamedRunSourcesRef.current) {
      if (!activeRequestIds.has(requestId)) {
        source.close();
        streamedRunSourcesRef.current.delete(requestId);
      }
    }

    for (const requestId of activeRequestIds) {
      if (streamedRunSourcesRef.current.has(requestId)) continue;
      const currentRun = visibleRuns.find(run => run.requestId === requestId);
      const isTerminal = currentRun?.status === 'completed' || currentRun?.status === 'failed';
      const lastEventId = isTerminal
        ? 0
        : Math.max(0, ...(currentRun?.parts || []).map(part => Number(part.id || 0)));
      const source = new EventSource(`/api/execution/runs/${encodeURIComponent(requestId)}/stream?afterId=${lastEventId}`);
      source.onmessage = event => {
        if (event.data === '[DONE]') {
          source.close();
          streamedRunSourcesRef.current.delete(requestId);
          return;
        }
        try {
          const chunk = JSON.parse(event.data);
          if (chunk.type === 'data-agent-event' || chunk.type === 'data-execution-event') {
            applyExecutionEvent(chunk.data);
          } else if (chunk.type === 'text-start') {
            streamedRunTextRef.current.set(requestId, '');
          } else if (chunk.type === 'text-delta') {
            const current = streamedRunTextRef.current.get(requestId) || '';
            streamedRunTextRef.current.set(requestId, current + (chunk.delta || ''));
          } else if (chunk.type === 'text-end') {
            const text = streamedRunTextRef.current.get(requestId) || '';
            streamedRunTextRef.current.delete(requestId);
            const completedRun = visibleRuns.find(run => run.requestId === requestId);
            appendExecutionMessage(
              requestId,
              text,
              `${completedRun?.title || completedRun?.memoryId || 'Task'} complete`,
            );
          }
        } catch (err) {
          console.error('Failed to parse execution stream event', err);
        }
      };
      source.onerror = () => {
        source.close();
        streamedRunSourcesRef.current.delete(requestId);
      };
      streamedRunSourcesRef.current.set(requestId, source);
    }

  }, [appendExecutionMessage, applyExecutionEvent, visibleRuns]);

  useEffect(() => {
    return () => {
      for (const source of streamedRunSourcesRef.current.values()) source.close();
      streamedRunSourcesRef.current.clear();
    };
  }, []);

  useEffect(() => {
    const detectAndStoreTimezone = async () => {
      if (settings.timezone) return;
      try {
        const browserTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
        const response = await fetch('/api/timezone', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ timezone: browserTimezone }),
        });
        if (response.ok) setSettings({ ...settings, timezone: browserTimezone });
      } catch (err) {
        console.debug('Timezone detection failed:', err);
      }
    };
    void detectAndStoreTimezone();
  }, [settings, setSettings]);

  const handleClearHistory = useCallback(async () => {
    const res = await fetch('/api/chat/history', { method: 'DELETE' });
    if (!res.ok) return;
    chat.setMessages([]);
    setExecutionRuns([]);
    executionMessageIdsRef.current.clear();
    knownExecutionRunIdsRef.current.clear();
    hasLoadedExecutionRunsRef.current = true;
  }, [chat]);

  const handleSubmit = useCallback(async () => {
    const value = input.trim();
    if (!value || isInteractionTurnActive) return;
    setInput('');
    setError(null);
    await (chat as any).sendMessage({ text: value });
  }, [chat, input, isInteractionTurnActive]);

  return (
    <main className="chat-bg min-h-screen p-4 sm:p-6">
      <div className="chat-wrap flex flex-col">
        <ChatHeader onOpenSettings={openSettings} onClearHistory={() => void handleClearHistory()} />

        <div className="grid min-h-0 flex-1 gap-3 lg:grid-cols-[minmax(0,1fr)_380px]">
          <div className="card min-h-0 overflow-hidden">
            <ChatMessages
              messages={messages}
              isWaitingForResponse={isWaitingForResponse}
              scrollContainerRef={scrollContainerRef}
              onScroll={handleScroll}
            />

            <div className="border-t border-gray-200 p-3">
              {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}

              <ChatInput
                value={input}
                canSubmit={canSubmitMessage}
                placeholder="Type a message..."
                onChange={setInput}
                onSubmit={handleSubmit}
              />
            </div>
          </div>

          <ExecutionDebugSidebar runs={visibleRuns} />
        </div>

        <SettingsModal open={open} onClose={closeSettings} settings={settings} onSave={setSettings} />
      </div>
    </main>
  );
}

function ExecutionDebugSidebar({ runs }: { runs: ExecutionRun[] }) {
  return (
    <aside className="card flex min-h-[240px] flex-col overflow-hidden lg:min-h-0">
      <div className="border-b border-gray-200 px-3 py-2">
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-sm font-semibold text-gray-900">Execution logs</h2>
          <span className="rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-600">{runs.length}</span>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto bg-gray-950 p-3 font-mono text-[11px] leading-5 text-gray-100">
        {runs.length === 0 ? (
          <div className="text-gray-400">No execution logs yet.</div>
        ) : (
          runs.map(run => <RawExecutionRun key={run.requestId || run.memoryId || run.title} run={run} />)
        )}
      </div>
    </aside>
  );
}

function RawExecutionRun({ run }: { run: ExecutionRun }) {
  const parts = Array.isArray(run.parts) ? run.parts : [];
  const statusColor =
    run.status === 'failed' || run.ok === false
      ? 'text-red-300'
      : run.status === 'completed'
        ? 'text-green-300'
        : 'text-amber-300';

  return (
    <div className="mb-4 border-b border-gray-800 pb-3 last:mb-0 last:border-b-0">
      <div className="mb-1 flex items-center justify-between gap-2">
        <span className="truncate font-semibold text-white">{run.title || run.memoryId || 'execution'}</span>
        <span className={statusColor}>{run.status || 'unknown'}</span>
      </div>
      <div className="mb-2 break-all text-gray-500">{run.requestId}</div>
      <div className="space-y-1.5">
        {parts.map((part, index) => (
          <ExecutionEventRow key={`${part.createdAt || ''}-${index}`} part={part} />
        ))}
      </div>
    </div>
  );
}

function ExecutionEventRow({ part }: { part: ExecutionPart }) {
  const status = part.state || part.type || 'event';
  const label = part.toolName || part.type || 'event';
  const detail = summarizeExecutionPart(part);
  const isError = part.state === 'output-error' || part.state === 'failed' || Boolean(part.error);
  const isDone = part.state === 'completed' || part.state === 'output-available';

  return (
    <div className="rounded bg-gray-900 px-2 py-1.5 text-gray-200">
      <div className="flex items-center justify-between gap-2">
        <span className="truncate font-semibold text-white">{label}</span>
        <span className={isError ? 'text-red-300' : isDone ? 'text-green-300' : 'text-amber-300'}>{status}</span>
      </div>
      {detail && <div className="mt-1 whitespace-pre-wrap break-words text-gray-400">{detail}</div>}
    </div>
  );
}

function summarizeExecutionPart(part: ExecutionPart): string {
  if (part.error) return `Error: ${part.error}`;
  if (part.output !== undefined && part.output !== null) return `Result: ${compactValue(part.output)}`;
  if (part.input !== undefined && part.input !== null) return `Input: ${compactValue(part.input)}`;
  if (part.text) return part.text;
  return '';
}

function compactValue(value: unknown): string {
  const text = typeof value === 'string' ? value : JSON.stringify(value, null, 0);
  if (!text) return '';
  const singleLine = text.replace(/\s+/g, ' ').trim();
  return singleLine.length > 180 ? `${singleLine.slice(0, 177)}...` : singleLine;
}
