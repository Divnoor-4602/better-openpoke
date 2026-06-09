import { auth } from '@clerk/tanstack-react-start/server'
import { redirect } from '@tanstack/react-router'
import { createServerFn } from '@tanstack/react-start'

export const getAuth = createServerFn({ method: 'GET' }).handler(async () => {
  const { getToken, isAuthenticated, userId } = await auth()
  const token = await getToken()

  return {
    isAuthenticated,
    token,
    userId,
  }
})

export const requireAuth = createServerFn({ method: 'GET' }).handler(
  async () => {
    const { isAuthenticated, userId } = await auth()

    if (!isAuthenticated) {
      throw redirect({
        to: '/sign-in/$',
      })
    }

    return { userId }
  },
)
