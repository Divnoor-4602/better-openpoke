import type {
  AssemblyAiSpeakerRevisionItem,
  AssemblyAiTurn,
} from './bridge/assemblyai-stream'

export type FinalizedTurn = AssemblyAiTurn & {
  endOfTurn: true
  listenerToken: string
  userId: string
}

export type SpeakerRevisionEvent = {
  listenerToken: string
  meetingId: string
  revisions: AssemblyAiSpeakerRevisionItem[]
  userId: string
}

export type TurnSink = {
  readonly onSpeakerRevision: (
    event: SpeakerRevisionEvent,
  ) => Promise<void> | void
  readonly onTurn: (turn: FinalizedTurn) => Promise<void> | void
}

export const consoleSink: TurnSink = {
  onSpeakerRevision(event) {
    console.log('[speaker-revision]', {
      count: event.revisions.length,
      meetingId: event.meetingId,
      revisions: event.revisions,
      userId: event.userId,
    })
  },
  onTurn(turn) {
    console.log('[turn]', {
      endMs: turn.endMs,
      meetingId: turn.meetingId,
      speaker: turn.speaker,
      startMs: turn.startMs,
      text: turn.transcript,
      turnOrder: turn.turnOrder,
      userId: turn.userId,
    })
  },
}
