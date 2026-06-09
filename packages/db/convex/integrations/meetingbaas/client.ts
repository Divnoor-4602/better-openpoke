import type { BaasClient } from '@meeting-baas/sdk'

import { createBaasClient } from '@meeting-baas/sdk'

import { validationError } from '../../error'
import { Bots } from './bots/bots'
import { Calendar } from './calendar/calendar'

export type MeetingBaasSdk = BaasClient<'v2'>

export class MeetingBaasClient {
  readonly bots: Bots
  readonly calendar: Calendar
  readonly sdk: MeetingBaasSdk

  constructor() {
    const apiKey = process.env.MEETINGBAAS_API_KEY
    if (!apiKey) {
      validationError({
        entity: 'MeetingBaasClient',
        message: 'MEETINGBAAS_API_KEY is not set',
      })
    }
    this.sdk = createBaasClient({ api_key: apiKey, api_version: 'v2' })
    this.bots = new Bots(this)
    this.calendar = new Calendar(this)
  }
}
