import { createFileRoute } from '@tanstack/react-router'

import { Welcome } from '@/features/home/components/welcome'

export const Route = createFileRoute('/_protected/')({ component: Welcome })
