// @ts-check

import { createEslintConfig } from '@general-poke/config'

export default [
  {
    ignores: ['convex/_generated/**'],
  },
  ...createEslintConfig({ rootUrl: import.meta.url }),
]
