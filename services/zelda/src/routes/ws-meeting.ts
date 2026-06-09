import type { Context } from 'hono'
import type { WSContext, WSEvents } from 'hono/ws'

import type { AppEnv } from '../context'
import type { SpeakerInfo } from '../session/manager'

import { verifyListenerToken } from '../auth/verify-token'

type SpeakerMessage = {
  id: unknown
  isSpeaking: unknown
  name: unknown
  timestamp: unknown
}

function parseSpeakerMessage(raw: string): null | SpeakerInfo {
  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch {
    return null
  }
  if (!parsed || typeof parsed !== 'object') return null
  const msg = parsed as SpeakerMessage
  if (
    typeof msg.id !== 'string' ||
    typeof msg.name !== 'string' ||
    typeof msg.isSpeaking !== 'boolean' ||
    typeof msg.timestamp !== 'number'
  ) {
    return null
  }
  return {
    id: msg.id,
    isSpeaking: msg.isSpeaking,
    name: msg.name,
    updatedAt: msg.timestamp,
  }
}

function rejectHandler(code: number, reason: string): WSEvents {
  return {
    onMessage: (_evt: MessageEvent, ws: WSContext) => {
      ws.close(code, reason)
    },
    onOpen: (_evt: Event, ws: WSContext) => {
      ws.close(code, reason)
    },
  }
}

export async function wsMeetingHandler(
  c: Context<AppEnv, '/ws/meeting/:meetingId'>,
): Promise<WSEvents> {
  const meetingId = c.req.param('meetingId')
  const token = c.req.query('token')
  if (!token) return rejectHandler(4401, 'missing_token')

  let claims
  try {
    claims = await verifyListenerToken(token)
  } catch {
    return rejectHandler(4401, 'invalid_token')
  }
  if (claims.meetingId !== meetingId) {
    return rejectHandler(4403, 'meeting_mismatch')
  }

  const session = await c.var.sessions.open({
    meetingId,
    userId: claims.userId,
  })
  console.log('[ws]', meetingId, 'session opened for', claims.userId)

  return {
    onClose: () => {
      console.log('[ws]', meetingId, 'connection closed')
      void session.terminate()
    },
    onError: (event) => {
      console.error('[ws]', meetingId, 'error', event)
    },
    onMessage: (event) => {
      const data = event.data
      if (typeof data === 'string') {
        const speaker = parseSpeakerMessage(data)
        if (speaker) session.updateSpeaker(speaker)
        return
      }
      if (data instanceof ArrayBuffer) {
        session.sendAudio(data)
        return
      }
      if (ArrayBuffer.isView(data)) {
        session.sendAudio(data.buffer)
      }
    },
  }
}
