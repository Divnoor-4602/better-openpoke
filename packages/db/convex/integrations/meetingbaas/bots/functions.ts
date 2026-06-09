import type { MeetingBaasClient } from '../client'
import type {
  DispatchBotInput,
  DispatchBotOutput,
  LeaveBotInput,
  LeaveBotOutput,
} from './schema'

import { validationError } from '../../../error'
import {
  DispatchBotInputSchema,
  DispatchBotOutputSchema,
  LeaveBotInputSchema,
  LeaveBotOutputSchema,
} from './schema'

const DEFAULT_BOT_NAME = 'Legal Poke'
const STREAMING_AUDIO_FREQUENCY = 24000

export async function dispatchBot(
  client: MeetingBaasClient,
  input: DispatchBotInput,
): Promise<DispatchBotOutput> {
  const args = DispatchBotInputSchema.parse(input)

  const res = await client.sdk.createBot({
    bot_name: args.botName ?? DEFAULT_BOT_NAME,
    callback_config: {
      method: 'POST',
      secret: args.webhookSecret,
      url: args.callbackUrl,
    },
    callback_enabled: true,
    meeting_url: args.meetingUrl,
    recording_mode: 'audio_only',
    streaming_config: {
      audio_frequency: STREAMING_AUDIO_FREQUENCY,
      input_url: args.listenerWsUrl,
    },
    streaming_enabled: true,
  })

  if (!res.success) {
    validationError({
      entity: 'MeetingBaasBot',
      message: `dispatchBot failed: ${res.message}`,
    })
  }

  const parsed = DispatchBotOutputSchema.safeParse({
    botId: res.data.bot_id,
  })
  if (!parsed.success) {
    validationError({
      entity: 'MeetingBaasBot',
      message: `dispatchBot response invalid: ${parsed.error.message}`,
    })
  }
  return parsed.data
}

export async function leaveBot(
  client: MeetingBaasClient,
  input: LeaveBotInput,
): Promise<LeaveBotOutput> {
  const args = LeaveBotInputSchema.parse(input)

  const res = await client.sdk.leaveBot({ bot_id: args.botId })

  if (!res.success) {
    validationError({
      entity: 'MeetingBaasBot',
      id: args.botId,
      message: `leaveBot failed: ${res.message}`,
    })
  }

  const parsed = LeaveBotOutputSchema.safeParse({
    botId: args.botId,
    ok: true,
  })
  if (!parsed.success) {
    validationError({
      entity: 'MeetingBaasBot',
      id: args.botId,
      message: `leaveBot response invalid: ${parsed.error.message}`,
    })
  }
  return parsed.data
}
