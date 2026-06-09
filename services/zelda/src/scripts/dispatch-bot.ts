import { randomUUID } from 'node:crypto'

import { createBaasClient } from '@meeting-baas/sdk'
import { SignJWT } from 'jose'

const meetingUrl = process.argv[2]
if (!meetingUrl) {
  console.error('usage: bun src/scripts/dispatch-bot.ts <meeting-url>')
  console.error('  e.g.: bun src/scripts/dispatch-bot.ts https://meet.google.com/abc-defg-hij')
  process.exit(1)
}

const apiKey = process.env.MEETINGBAAS_API_KEY
const jwtSecret = process.env.ZELDA_JWT_SECRET
const publicUrl = process.env.ZELDA_PUBLIC_URL
const webhookSecret = process.env.MEETINGBAAS_WEBHOOK_SECRET

if (!apiKey || !jwtSecret || !publicUrl || !webhookSecret) {
  console.error(
    'set MEETINGBAAS_API_KEY, MEETINGBAAS_WEBHOOK_SECRET, ZELDA_JWT_SECRET, ZELDA_PUBLIC_URL',
  )
  console.error('  ZELDA_PUBLIC_URL must be a publicly reachable https URL pointing at this local zelda (use ngrok / cloudflared / tailscale funnel)')
  process.exit(1)
}

const meetingId = randomUUID()
const userId = `test-user-${randomUUID().slice(0, 8)}`

const token = await new SignJWT({ meetingId, scope: 'zelda-listener' })
  .setProtectedHeader({ alg: 'HS256', typ: 'JWT' })
  .setIssuer('convex')
  .setAudience('zelda')
  .setSubject(userId)
  .setIssuedAt()
  .setExpirationTime('11100s')
  .sign(new TextEncoder().encode(jwtSecret))

const wsUrl = `${publicUrl.replace(/^http/, 'ws')}/ws/meeting/${meetingId}?token=${token}`
const webhookUrl = `${publicUrl.replace(/\/$/, '')}/webhooks/meetingbaas`

console.log('meetingId  :', meetingId)
console.log('userId     :', userId)
console.log('wsUrl      :', `${wsUrl.slice(0, 80)}...`)
console.log('webhookUrl :', webhookUrl)
console.log('meetingUrl :', meetingUrl)
console.log()

const client = createBaasClient({ api_key: apiKey, api_version: 'v2' })

const result = await client.createBot({
  bot_name: 'Zelda Test Bot',
  callback_config: { method: 'POST', secret: webhookSecret, url: webhookUrl },
  callback_enabled: true,
  meeting_url: meetingUrl,
  recording_mode: 'audio_only',
  streaming_config: { audio_frequency: 24000, input_url: wsUrl },
  streaming_enabled: true,
})

console.log('dispatch result:', JSON.stringify(result, null, 2))

if (result.success) {
  console.log()
  console.log('bot dispatched. watch zelda logs for:')
  console.log('  [ws] <meetingId> session opened ...')
  console.log('  [turn] { ... }')
  console.log()
  console.log('to stop the bot manually, run:')
  console.log(`  bun src/scripts/leave-bot.ts ${result.data?.bot_id ?? '<bot-id>'}`)
}
