import { createApp, websocket } from './app'
import { createSessionManager } from './session/manager'
import { consoleSink } from './sink'

const assemblyAiKey = process.env.ASSEMBLYAI_API_KEY
if (!assemblyAiKey) {
  console.error('ASSEMBLYAI_API_KEY is not set')
  process.exit(1)
}

const sessions = createSessionManager({
  assemblyAiKey,
  sink: consoleSink,
})

const app = createApp({ sessions })

const port = Number(process.env.PORT ?? 8787)

const server = Bun.serve({
  fetch: app.fetch,
  port,
  websocket,
})

console.log(`zelda listening on http://localhost:${server.port}`)

async function shutdown(signal: string) {
  console.log(`received ${signal}, terminating sessions...`)
  await sessions.shutdown()
  await server.stop(true)
  process.exit(0)
}

process.on('SIGINT', () => void shutdown('SIGINT'))
process.on('SIGTERM', () => void shutdown('SIGTERM'))
