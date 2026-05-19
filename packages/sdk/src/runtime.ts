import type { CreateClientConfig } from './generated/client.gen';

export const DEFAULT_OPENPOKE_BASE_URL = 'http://localhost:8001';

const envBaseUrl: string | undefined =
  typeof import.meta === 'undefined'
    ? undefined
    : (import.meta as { env?: Record<string, string | undefined> }).env
        ?.VITE_API_URL;

export const resolveBaseUrl = (override?: string): string =>
  override ?? envBaseUrl ?? DEFAULT_OPENPOKE_BASE_URL;

let authToken: null | string = null;
const subscribers = new Set<(token: null | string) => void>();

export const setAuthToken = (token: null | string) => {
  authToken = token;
  for (const subscriber of subscribers) subscriber(token);
};

export const getAuthToken = () => authToken;

export const subscribeAuthToken = (subscriber: (token: null | string) => void) => {
  subscribers.add(subscriber);
  return () => {
    subscribers.delete(subscriber);
  };
};

export const createAuthedFetch = (
  base: typeof globalThis.fetch = globalThis.fetch,
): typeof globalThis.fetch =>
  ((input, init) => {
    // hey-api calls fetch(new Request(...)) with no init, so we must not clobber
    // the request's existing headers/body. Inject Authorization only if missing.
    if (input instanceof Request) {
      if (!authToken || input.headers.has('Authorization')) return base(input);
      const headers = new Headers(input.headers);
      headers.set('Authorization', `Basic ${authToken}`);
      return base(new Request(input, { headers }));
    }
    const headers = new Headers(init?.headers);
    if (authToken && !headers.has('Authorization')) {
      headers.set('Authorization', `Basic ${authToken}`);
    }
    return base(input, { ...init, headers });
  }) as typeof globalThis.fetch;

export const createClientConfig: CreateClientConfig = (config) => ({
  ...config,
  baseUrl: resolveBaseUrl(config?.baseUrl),
  fetch: createAuthedFetch(config?.fetch),
});
