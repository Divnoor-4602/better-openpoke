import { createFileRoute, Outlet } from '@tanstack/react-router'

import { requireAuth } from '../lib/integrations/clerk/server'

export const Route = createFileRoute('/_protected')({
  beforeLoad: async () => {
    return await requireAuth()
  },
  component: ProtectedLayout,
})

function ProtectedLayout() {
  return <Outlet />
}
