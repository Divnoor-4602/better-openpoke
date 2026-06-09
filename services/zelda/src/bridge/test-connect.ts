import { createAssemblyAiStream } from './assemblyai-stream'

const apiKey = process.env.ASSEMBLYAI_API_KEY
if (!apiKey) {
  console.error('set ASSEMBLYAI_API_KEY')
  process.exit(1)
}

const stream = createAssemblyAiStream({
  apiKey,
  meetingId: 'test-meeting',
  onError: (err) => console.error('[error]', err.message),
  onTurn: (turn) => console.log('[turn]', turn),
})

console.log('waiting for Begin...')
await stream.ready
console.log('session ready:', stream.sessionId())

// 50ms of silence at 16kHz mono s16le = 1600 bytes of zeros
const silence = new ArrayBuffer(1600)
const framesToSend = 60 // 3 seconds

for (let i = 0; i < framesToSend; i++) {
  stream.sendAudio(silence)
  await new Promise((r) => setTimeout(r, 50))
}

console.log('terminating...')
await stream.terminate()
console.log('done')
