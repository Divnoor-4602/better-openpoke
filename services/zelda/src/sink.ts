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

// consoleSink logs metadata only — transcript content is intentionally NOT
// included (compliance §3: no sensitive content in logs).
export const consoleSink: TurnSink = {
  onSpeakerRevision(event) {
    console.log('[turn-sink] revision', {
      count: event.revisions.length,
      meetingId: event.meetingId,
      userId: event.userId,
    })
  },
  onTurn(turn) {
    console.log('[turn-sink] turn', {
      endMs: turn.endMs,
      meetingId: turn.meetingId,
      speaker: turn.speaker,
      startMs: turn.startMs,
      textLength: turn.transcript.length,
      turnOrder: turn.turnOrder,
      userId: turn.userId,
    })
  },
}
