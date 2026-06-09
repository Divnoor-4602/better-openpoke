export function stripUndefined<T extends object>(input: T): Partial<T> {
  const out: Partial<T> = {}
  for (const key of Object.keys(input) as (keyof T)[]) {
    const value = input[key]
    if (value !== undefined) {
      out[key] = value
    }
  }
  return out
}
