import { createBaasClient } from '@meeting-baas/sdk'

const botId = process.argv[2]
if (!botId) {
  console.error('usage: bun src/scripts/leave-bot.ts <bot-id>')
  process.exit(1)
}

const apiKey = process.env.MEETINGBAAS_API_KEY
if (!apiKey) {
  console.error('set MEETINGBAAS_API_KEY')
  process.exit(1)
}

const client = createBaasClient({ api_key: apiKey, api_version: 'v2' })
const result = await client.leaveBot({ bot_id: botId })

console.log('leave result:', JSON.stringify(result, null, 2))
