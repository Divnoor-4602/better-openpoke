import { useEffect, useEffectEvent } from 'react'

export function useTimeout(callback: () => void, delay?: null | number) {
  const onTimeout = useEffectEvent(callback)

  useEffect(() => {
    if (typeof delay !== 'number') return

    const timeoutId = window.setTimeout(onTimeout, delay)

    return () => {
      window.clearTimeout(timeoutId)
    }
  }, [delay])
}
