import type { Context } from 'hono'
import type { WSContext, WSEvents } from 'hono/ws'

import type { AppEnv } from '../context'
import type { SpeakerInfo } from '../session/manager'

import { verifyListenerToken } from '../auth/verify-token'
import {
  notifyMeetingEnded,
  notifyMeetingRecording,
} from '../sinks/convex-sink'

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
    listenerToken: token,
    meetingId,
    userId: claims.userId,
  })
  console.log('[ws]', meetingId, 'session opened — AAI ready, marking recording')
  void notifyMeetingRecording({ listenerToken: token, meetingId })

  let binaryFramesReceived = 0
  let totalBytesReceived = 0
  let lastFrameLogAt = 0
  let speakerJsonReceived = 0
  let firstFrameLogged = false
  let firstTextLogged = false

  return {
    onClose: (event) => {
      console.log('[ws]', meetingId, 'connection closed', {
        binaryFramesReceived,
        code: event.code,
        reason: event.reason,
        speakerJsonReceived,
        totalBytesReceived,
      })
      void notifyMeetingEnded({
        listenerToken: token,
        meetingId,
      })
      void session.terminate()
    },
    onError: (event) => {
      console.error('[ws]', meetingId, 'error', event)
    },
    onMessage: (event) => {
      const data = event.data
      if (typeof data === 'string') {
        speakerJsonReceived += 1
        if (!firstTextLogged) {
          firstTextLogged = true
          console.log('[ws]', meetingId, 'first text frame', {
            length: data.length,
            preview: data.slice(0, 80),
          })
        }
        const speaker = parseSpeakerMessage(data)
        if (speaker) session.updateSpeaker(speaker)
        return
      }
      const view = toUint8(data)
      if (!view) {
        if (!firstFrameLogged) {
          firstFrameLogged = true
          console.warn('[ws]', meetingId, 'unknown frame type', {
            ctor: (data as { constructor?: { name?: string } })?.constructor
              ?.name,
            typeofData: typeof data,
          })
        }
        return
      }
      binaryFramesReceived += 1
      totalBytesReceived += view.byteLength
      if (!firstFrameLogged) {
        firstFrameLogged = true
        const sampleBytes = Array.from(view.slice(0, 16))
        console.log('[ws]', meetingId, 'first binary frame', {
          byteLength: view.byteLength,
          ctor: (data as { constructor?: { name?: string } })?.constructor
            ?.name,
          firstBytes: sampleBytes,
        })
      }
      const now = Date.now()
      if (now - lastFrameLogAt > 5000) {
        console.log('[ws]', meetingId, 'audio frames', {
          count: binaryFramesReceived,
          totalBytes: totalBytesReceived,
        })
        lastFrameLogAt = now
      }
      session.sendAudio(view)
    },
  }
}

function toUint8(data: unknown): null | Uint8Array {
  if (data instanceof Uint8Array) return data
  if (data instanceof ArrayBuffer) return new Uint8Array(data)
  if (ArrayBuffer.isView(data)) {
    const v = data as ArrayBufferView
    return new Uint8Array(v.buffer, v.byteOffset, v.byteLength)
  }
  return null
}
