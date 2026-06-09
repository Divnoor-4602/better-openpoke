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
  turnOrder: number
}

export type AssemblyAiSpeakerRevisionItem = {
  speaker: null | string
  turnOrder: number
}

export type AssemblyAiSpeakerRevision = {
  meetingId: string
  revisions: AssemblyAiSpeakerRevisionItem[]
}

export type AssemblyAiStreamOptions = {
  apiKey: string
  meetingId: string
  onError?: (err: Error) => void
  onSpeakerRevision?: (event: AssemblyAiSpeakerRevision) => void
  onTurn: (turn: AssemblyAiTurn) => void
}

export type AssemblyAiStream = {
  readonly ready: Promise<void>
  readonly sendAudio: (frame: ArrayBufferLike | Uint8Array) => void
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
    sampleRate: 24_000,
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
    // Diagnostic: log Turn arrivals with metadata only (no text content).
    console.log('[aai]', opts.meetingId, 'turn', {
      endOfTurn: turn.end_of_turn,
      textLength: turn.transcript.length,
      turnOrder: turn.turn_order,
    })
    opts.onTurn({
      endMs,
      endOfTurn: turn.end_of_turn,
      isFormatted: turn.turn_is_formatted,
      meetingId: opts.meetingId,
      speaker: turn.speaker_label ?? null,
      startMs,
      transcript: turn.transcript,
      turnOrder: turn.turn_order,
    })
  })

  transcriber.on('speakerRevision', (event) => {
    if (!opts.onSpeakerRevision) return
    opts.onSpeakerRevision({
      meetingId: opts.meetingId,
      revisions: event.revisions.map((r) => ({
        speaker: r.speaker_label ?? null,
        turnOrder: r.turn_order,
      })),
    })
  })

  transcriber.on('error', (err) => {
    console.error('[aai]', opts.meetingId, 'error', err)
    opts.onError?.(err)
  })

  transcriber.on('close', (code, reason) => {
    console.log('[aai]', opts.meetingId, 'closed', { code, reason })
  })

  void transcriber.connect()

  return {
    ready,
    sendAudio(frame) {
      transcriber.sendAudio(frame as ArrayBufferLike)
    },
    sessionId: () => sessionId,
    async terminate() {
      await transcriber.close()
    },
  }
}
