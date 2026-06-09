import type { MeetingBaasClient } from '../client'
import type {
  CreateConnectionInput,
  CreateConnectionOutput,
  DeleteCalendarBotInput,
  DeleteCalendarBotOutput,
  DeleteConnectionInput,
  DeleteConnectionOutput,
  ListEventsInput,
  ListEventsOutput,
  ScheduleBotInput,
  ScheduleBotOutput,
} from './schema'

import {
  createConnection,
  deleteCalendarBot,
  deleteConnection,
  listEvents,
  scheduleBot,
} from './functions'

export class Calendar {
  constructor(private readonly client: MeetingBaasClient) {}

  createConnection(
    input: CreateConnectionInput,
  ): Promise<CreateConnectionOutput> {
    return createConnection(this.client, input)
  }

  deleteCalendarBot(
    input: DeleteCalendarBotInput,
  ): Promise<DeleteCalendarBotOutput> {
    return deleteCalendarBot(this.client, input)
  }

  deleteConnection(
    input: DeleteConnectionInput,
  ): Promise<DeleteConnectionOutput> {
    return deleteConnection(this.client, input)
  }

  listEvents(input: ListEventsInput): Promise<ListEventsOutput> {
    return listEvents(this.client, input)
  }

  scheduleBot(input: ScheduleBotInput): Promise<ScheduleBotOutput> {
    return scheduleBot(this.client, input)
  }
}
