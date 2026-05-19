import { useEffect } from 'react'

export function useMountEffect(effect: () => (() => void) | void) {
  /* eslint-disable react-hooks/exhaustive-deps */
  useEffect(effect, [])
}
