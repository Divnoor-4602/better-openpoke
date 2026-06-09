import type { MeetingBaasClient } from '../client'
import type {
  DispatchBotInput,
  DispatchBotOutput,
  LeaveBotInput,
  LeaveBotOutput,
} from './schema'

import { dispatchBot, leaveBot } from './functions'

export class Bots {
  constructor(private readonly client: MeetingBaasClient) {}

  dispatch(input: DispatchBotInput): Promise<DispatchBotOutput> {
    return dispatchBot(this.client, input)
  }

  leave(input: LeaveBotInput): Promise<LeaveBotOutput> {
    return leaveBot(this.client, input)
  }
}
