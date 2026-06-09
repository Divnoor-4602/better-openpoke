// Generates apps/server/generated/tool_schemas.json from the catalog's Zod
// schemas. Runs as a predev/prebuild hook so the checked-in JSON tracks
// schemas.ts automatically. The Python server reads the JSON at import
// time — see apps/server/agents/tool_schemas.py.

import { mkdirSync, writeFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { z } from 'zod'

import { TOOL_SCHEMAS } from '../src/features/assistant/components/catalog/schemas'

const here = dirname(fileURLToPath(import.meta.url))
const target = resolve(here, '../../../apps/server/generated/tool_schemas.json')

const out = Object.fromEntries(
  Object.entries(TOOL_SCHEMAS).map(([name, { strict }]) => [
    name,
    z.toJSONSchema(strict),
  ]),
)

mkdirSync(dirname(target), { recursive: true })
writeFileSync(target, JSON.stringify(out, null, 2) + '\n')
console.log(`wrote ${Object.keys(out).length} tool schemas → ${target}`)
