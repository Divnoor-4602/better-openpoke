import type { CreateClientConfig } from './generated/client.gen';

export const DEFAULT_OPENPOKE_BASE_URL = 'http://localhost:8001';

export const createClientConfig: CreateClientConfig = (config) => ({
  ...config,
  baseUrl: config?.baseUrl ?? DEFAULT_OPENPOKE_BASE_URL,
});
