import { z } from 'zod'

export const DispatchBotInputSchema = z.object({
  botName: z.string().optional(),
  callbackUrl: z.url(),
  listenerWsUrl: z.string(),
  meetingUrl: z.url(),
  webhookSecret: z.string(),
})
export type DispatchBotInput = z.infer<typeof DispatchBotInputSchema>

export const DispatchBotOutputSchema = z.object({
  botId: z.string(),
})
export type DispatchBotOutput = z.infer<typeof DispatchBotOutputSchema>

export const LeaveBotInputSchema = z.object({
  botId: z.string(),
})
export type LeaveBotInput = z.infer<typeof LeaveBotInputSchema>

export const LeaveBotOutputSchema = z.object({
  botId: z.string(),
  ok: z.literal(true),
})
export type LeaveBotOutput = z.infer<typeof LeaveBotOutputSchema>
