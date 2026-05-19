import { z } from 'zod'

export const loginSchema = z.object({
  handle: z
    .string()
    .trim()
    .min(1, 'Username required')
    .max(64, 'Username too long')
    .regex(/^[a-zA-Z0-9_-]+$/, 'Invalid characters'),
  password: z.string().min(1, 'Password required'),
})

export type LoginInput = z.infer<typeof loginSchema>
