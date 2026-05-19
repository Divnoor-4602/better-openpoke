import type { ThreadResource } from '@openpoke/sdk'

export type ThreadGroup = {
  items: ThreadResource[]
  label: null | string
}

const DAY_MS = 1000 * 60 * 60 * 24

/**
 * Bucket threads by how recently they were last touched (`updatedAt`).
 * Buckets are non-overlapping calendar-day windows in the user's local time.
 * Empty groups are dropped, so headers only render when they have items.
 * Within each bucket, threads are sorted newest-first.
 */
export function groupThreadsByRecency(
  threads: ThreadResource[],
): ThreadGroup[] {
  const todayStart = startOfLocalDay(new Date())

  const today: ThreadResource[] = []
  const yesterday: ThreadResource[] = []
  const lastWeek: ThreadResource[] = []
  const lastTwoWeeks: ThreadResource[] = []
  const lastMonth: ThreadResource[] = []
  const older: ThreadResource[] = []

  for (const thread of threads) {
    const updatedDayStart = startOfLocalDay(new Date(thread.updatedAt))
    const daysAgo = Math.round((todayStart - updatedDayStart) / DAY_MS)

    if (daysAgo <= 0) today.push(thread)
    else if (daysAgo === 1) yesterday.push(thread)
    else if (daysAgo <= 7) lastWeek.push(thread)
    else if (daysAgo <= 14) lastTwoWeeks.push(thread)
    else if (daysAgo <= 30) lastMonth.push(thread)
    else older.push(thread)
  }

  const newestFirst = (a: ThreadResource, b: ThreadResource) =>
    new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime()

  const groups: ThreadGroup[] = [
    { items: today.sort(newestFirst), label: 'Today' },
    { items: yesterday.sort(newestFirst), label: 'Yesterday' },
    { items: lastWeek.sort(newestFirst), label: 'Last week' },
    { items: lastTwoWeeks.sort(newestFirst), label: 'Last 2 weeks' },
    { items: lastMonth.sort(newestFirst), label: 'Last month' },
    { items: older.sort(newestFirst), label: 'Older' },
  ]

  return groups.filter((group) => group.items.length > 0)
}

function startOfLocalDay(date: Date): number {
  const d = new Date(date)
  d.setHours(0, 0, 0, 0)
  return d.getTime()
}
