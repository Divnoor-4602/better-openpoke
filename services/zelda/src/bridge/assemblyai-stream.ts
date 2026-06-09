import type { StreamingPiiPolicy } from 'assemblyai'

import { AssemblyAI } from 'assemblyai'

const PII_POLICIES: StreamingPiiPolicy[] = [
  'person_name',
  'phone_number',
  'email_address',
  'credit_card_number',
  'us_social_security_number',
  'date_of_birth',
]

export type AssemblyAiTurn = {
  endMs: null | number
  endOfTurn: boolean
  isFormatted: boolean
  meetingId: string
  speaker: null | string
  startMs: null | number
  transcript: string
}

export type AssemblyAiStreamOptions = {
  apiKey: string
  meetingId: string
  onError?: (err: Error) => void
  onTurn: (turn: AssemblyAiTurn) => void
}

export type AssemblyAiStream = {
  readonly ready: Promise<void>
  readonly sendAudio: (frame: ArrayBufferLike) => void
  readonly sessionId: () => null | string
  readonly terminate: () => Promise<void>
}

export function createAssemblyAiStream(
  opts: AssemblyAiStreamOptions,
): AssemblyAiStream {
  const client = new AssemblyAI({ apiKey: opts.apiKey })
  const transcriber = client.streaming.transcriber({
    formatTurns: true,
    maxSpeakers: 10,
    redactPii: true,
    redactPiiPolicies: PII_POLICIES,
    redactPiiSub: 'entity_name',
    sampleRate: 16_000,
    speakerLabels: true,
    speechModel: 'u3-rt-pro',
  })

  let sessionId: null | string = null

  const ready = new Promise<void>((resolve, reject) => {
    transcriber.on('open', ({ id }) => {
      sessionId = id
      resolve()
    })
    transcriber.on('close', (code, reason) => {
      if (!sessionId) reject(new Error(`closed before open: ${code} ${reason}`))
    })
    transcriber.on('error', (err) => {
      if (!sessionId) reject(err)
    })
  })

  transcriber.on('turn', (turn) => {
    const startMs = turn.words[0]?.start ?? null
    const endMs = turn.words.at(-1)?.end ?? null
    opts.onTurn({
      endMs,
      endOfTurn: turn.end_of_turn,
      isFormatted: turn.turn_is_formatted,
      meetingId: opts.meetingId,
      speaker: turn.speaker_label ?? null,
      startMs,
      transcript: turn.transcript,
    })
  })

  transcriber.on('error', (err) => {
    opts.onError?.(err)
  })

  void transcriber.connect()

  return {
    ready,
    sendAudio(frame) {
      transcriber.sendAudio(frame)
    },
    sessionId: () => sessionId,
    async terminate() {
      await transcriber.close()
    },
  }
}
