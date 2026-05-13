//  @ts-check

import { tanstackConfig } from '@tanstack/eslint-config'
import eslintConfigPrettier from 'eslint-config-prettier'
import checkFile from 'eslint-plugin-check-file'
import jsxA11y from 'eslint-plugin-jsx-a11y'
import perfectionist from 'eslint-plugin-perfectionist'
import prettier from 'eslint-plugin-prettier'
import react from 'eslint-plugin-react'
import reactHooks from 'eslint-plugin-react-hooks'
import { readdirSync } from 'node:fs'

const featureDirs = readdirSync(new URL('./src/features', import.meta.url), {
  withFileTypes: true,
})
  .filter((entry) => entry.isDirectory())
  .map((entry) => entry.name)

const featureIsolationZones = featureDirs.map((featureName) => ({
  except: [`./${featureName}`],
  from: './src/features',
  target: `./src/features/${featureName}`,
}))

export default [
  ...tanstackConfig,
  perfectionist.configs['recommended-natural'],
  eslintConfigPrettier,
  {
    rules: {
      'import/order': 'off',
      'sort-imports': 'off',
    },
  },
  {
    files: ['*.config.js'],
    languageOptions: {
      parserOptions: {
        project: false,
      },
    },
    rules: {
      '@typescript-eslint/no-unnecessary-condition': 'off',
      '@typescript-eslint/no-unnecessary-type-assertion': 'off',
      '@typescript-eslint/require-await': 'off',
    },
  },
  {
    files: ['**/*.{ts,tsx}'],
    plugins: {
      'check-file': checkFile,
      'jsx-a11y': jsxA11y,
      prettier,
      react,
      'react-hooks': reactHooks,
    },
    rules: {
      ...react.configs.recommended.rules,
      ...reactHooks.configs.recommended.rules,
      ...jsxA11y.configs.recommended.rules,
      '@typescript-eslint/array-type': 'off',
      '@typescript-eslint/no-explicit-any': 'off',
      '@typescript-eslint/require-await': 'off',
      'import/default': 'off',
      'import/no-cycle': 'error',
      'import/no-named-as-default': 'off',
      'import/no-named-as-default-member': 'off',
      'import/order': 'off',
      'perfectionist/sort-imports': [
        'error',
        {
          order: 'asc',
          type: 'natural',
        },
      ],
      'sort-imports': 'off',
      ...(featureIsolationZones.length > 0
        ? {
            'import/no-restricted-paths': [
              'error',
              {
                zones: featureIsolationZones,
              },
            ],
          }
        : {}),
      'jsx-a11y/anchor-is-valid': 'off',
      'pnpm/json-enforce-catalog': 'off',
      'prettier/prettier': ['error', {}, { usePrettierrc: true }],
      'react/prop-types': 'off',
      'react/react-in-jsx-scope': 'off',
    },
    settings: {
      react: {
        version: 'detect',
      },
    },
  },
  {
    files: ['src/**/*.{ts,tsx}'],
    ignores: ['src/routes/**', 'src/routeTree.gen.ts'],
    plugins: {
      'check-file': checkFile,
    },
    rules: {
      'check-file/filename-naming-convention': [
        'error',
        {
          '**/*.{ts,tsx}': 'KEBAB_CASE',
        },
        {
          ignoreMiddleExtensions: true,
        },
      ],
    },
  },
  {
    files: ['src/**/!(__tests__)/*'],
    plugins: {
      'check-file': checkFile,
    },
    rules: {
      'check-file/folder-naming-convention': [
        'error',
        {
          '**/*': 'KEBAB_CASE',
        },
      ],
    },
  },
]
