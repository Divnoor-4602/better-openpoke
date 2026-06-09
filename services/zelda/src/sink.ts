import type { AssemblyAiTurn } from './bridge/assemblyai-stream'

export type FinalizedTurn = AssemblyAiTurn & {
  endOfTurn: true
  userId: string
}

export type TurnSink = {
  readonly onTurn: (turn: FinalizedTurn) => Promise<void> | void
}

export const consoleSink: TurnSink = {
  onTurn(turn) {
    console.log('[turn]', {
      endMs: turn.endMs,
      meetingId: turn.meetingId,
      speaker: turn.speaker,
      startMs: turn.startMs,
      text: turn.transcript,
      userId: turn.userId,
    })
  },
}
