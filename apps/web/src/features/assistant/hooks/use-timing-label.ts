import { useEffect, useState } from 'react'

import { formatElapsed } from '../lib/format-time'

type Params = {
  completedAt?: number
  isRunning: boolean
  startedAt?: number
}

// Live elapsed string while running ("12s"), total duration once done ("2m 30s").
export const useTimingLabel = ({
  completedAt,
  isRunning,
  startedAt,
}: Params): null | string => {
  const [now, setNow] = useState<number>(() => Date.now())

  useEffect(() => {
    if (!isRunning || startedAt === undefined) return
    const id = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(id)
  }, [isRunning, startedAt])

  if (isRunning) {
    if (startedAt === undefined) return null
    return formatElapsed(now - startedAt)
  }
  if (startedAt === undefined || completedAt === undefined) return null
  return formatElapsed(completedAt - startedAt)
}
