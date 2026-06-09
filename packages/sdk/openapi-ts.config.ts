import { defineConfig } from '@hey-api/openapi-ts';

export default defineConfig({
  input: '../../apps/server/generated/openapi.json',
  output: {
    clean: true,
    path: './src/generated',
  },
  parser: {
    hooks: {
      operations: {
        getKind: (operation) => {
          if (operation.path === '/api/integrations/{provider}/status') {
            return ['query'];
          }

          if (operation.path.endsWith('/stream')) {
            return [];
          }

          return undefined;
        },
      },
    },
  },
  plugins: [
    '@hey-api/typescript',
    {
      name: 'zod',
      definitions: true,
      requests: true,
      responses: true,
    },
    {
      name: '@hey-api/sdk',
      operations: {
        strategy: 'flat',
      },
      validator: true,
    },
    {
      name: '@hey-api/client-fetch',
      runtimeConfigPath: './src/runtime.ts',
    },
    {
      name: '@tanstack/react-query',
      infiniteQueryKeys: true,
      infiniteQueryOptions: true,
      mutationOptions: true,
      queryKeys: {
        tags: true,
      },
      queryOptions: true,
    },
  ],
});
