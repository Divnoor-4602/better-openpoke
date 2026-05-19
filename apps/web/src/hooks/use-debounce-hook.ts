import { useEffect, useRef, useState } from 'react'

export function useDebounce<T>(value: T, delay: number): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value)

  useEffect(() => {
    const handler = setTimeout(() => {
      setDebouncedValue(value)
    }, delay)

    return () => {
      clearTimeout(handler)
    }
  }, [value, delay])

  return debouncedValue
}

export function useDebouncedCallback<TArgs extends unknown[]>(
  callback: (...args: TArgs) => void,
  delay: number,
): (...args: TArgs) => void {
  const timerRef = useRef<null | ReturnType<typeof setTimeout>>(null)

  const callbackRef = useRef(callback)
  useEffect(() => {
    callbackRef.current = callback
  })

  // Cleanup any pending timer on unmount.
  useEffect(
    () => () => {
      if (timerRef.current) clearTimeout(timerRef.current)
    },
    [],
  )

  return (...args: TArgs) => {
    if (timerRef.current) clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => callbackRef.current(...args), delay)
  }
}
