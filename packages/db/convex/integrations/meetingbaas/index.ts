import { MeetingBaasClient } from './client'

export const mb = new MeetingBaasClient()

export type {
  DispatchBotInput,
  DispatchBotOutput,
  LeaveBotInput,
  LeaveBotOutput,
} from './bots/schema'

export type {
  CalendarEvent,
  CalendarEventStatus,
  CalendarMeetingPlatform,
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
} from './calendar/schema'

export { MeetingBaasClient } from './client'
