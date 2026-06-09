import { cronJobs } from 'convex/server'

import { internal } from './_generated/api'

const crons = cronJobs()

crons.interval(
  'fail-stuck-meetings',
  { minutes: 15 },
  internal.meeting.jobs.failStuckMeetings,
  {},
)

export default crons
