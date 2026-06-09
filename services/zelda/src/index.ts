import { createApp, websocket } from './app'
import { createSessionManager } from './session/manager'
import { consoleSink } from './sink'
import { createConvexSink } from './sinks/convex-sink'

const assemblyAiKey = process.env.ASSEMBLYAI_API_KEY
if (!assemblyAiKey) {
  console.error('ASSEMBLYAI_API_KEY is not set')
  process.exit(1)
}

const convexUrl = process.env.CONVEX_URL
const sink = convexUrl ? createConvexSink({ convexUrl }) : consoleSink
if (!convexUrl) {
  console.warn('CONVEX_URL not set — using consoleSink (turns will not persist)')
}

const sessions = createSessionManager({
  assemblyAiKey,
  sink,
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
