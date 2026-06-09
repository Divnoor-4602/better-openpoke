import type { AssemblyAiStream } from '../bridge/assemblyai-stream'
import type { TurnSink } from '../sink'

import { createAssemblyAiStream } from '../bridge/assemblyai-stream'

export type SessionState = 'closed' | 'connecting' | 'streaming'

export type SpeakerInfo = {
  id: string
  isSpeaking: boolean
  name: string
  updatedAt: number
}

export type Session = {
  readonly currentSpeaker: () => null | SpeakerInfo
  readonly meetingId: string
  readonly sendAudio: (frame: ArrayBufferLike) => void
  readonly startedAt: number
  readonly state: () => SessionState
  readonly terminate: () => Promise<void>
  readonly updateSpeaker: (info: SpeakerInfo) => void
  readonly userId: string
  readonly utteranceCount: () => number
}

export type SessionManagerOptions = {
  assemblyAiKey: string
  sink: TurnSink
}

export type SessionManager = {
  readonly get: (meetingId: string) => Session | undefined
  readonly list: () => Session[]
  readonly open: (args: {
    meetingId: string
    userId: string
  }) => Promise<Session>
  readonly shutdown: () => Promise<void>
}

export function createSessionManager(
  opts: SessionManagerOptions,
): SessionManager {
  const sessions = new Map<string, Session>()

  async function open(args: { meetingId: string; userId: string }) {
    const existing = sessions.get(args.meetingId)
    if (existing) return existing

    let state: SessionState = 'connecting'
    let speaker: null | SpeakerInfo = null
    let utterances = 0
    let stream: AssemblyAiStream | null = null

    stream = createAssemblyAiStream({
      apiKey: opts.assemblyAiKey,
      meetingId: args.meetingId,
      onError: (err) => {
        console.error('[session]', args.meetingId, 'aai error', err.message)
      },
      onTurn: (turn) => {
        if (!turn.endOfTurn) return
        utterances += 1
        // Use speaker label from AAI; fall back to MeetingBaas hint if AAI didn't tag.
        const finalSpeaker = turn.speaker ?? speaker?.name ?? null
        void opts.sink.onTurn({
          ...turn,
          endOfTurn: true,
          speaker: finalSpeaker,
          userId: args.userId,
        })
      },
    })

    await stream.ready
    state = 'streaming'

    const session: Session = {
      currentSpeaker: () => speaker,
      meetingId: args.meetingId,
      sendAudio: (frame) => stream!.sendAudio(frame),
      startedAt: Date.now(),
      state: () => state,
      terminate: async () => {
        if (state === 'closed') return
        state = 'closed'
        await stream!.terminate()
        sessions.delete(args.meetingId)
      },
      updateSpeaker: (info) => {
        speaker = info
      },
      userId: args.userId,
      utteranceCount: () => utterances,
    }
    sessions.set(args.meetingId, session)
    return session
  }

  async function shutdown() {
    const all = [...sessions.values()]
    await Promise.allSettled(all.map((s) => s.terminate()))
    sessions.clear()
  }

  return {
    get: (id) => sessions.get(id),
    list: () => [...sessions.values()],
    open,
    shutdown,
  }
}
