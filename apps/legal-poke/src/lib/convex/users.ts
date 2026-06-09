import { api } from '@general-poke/db/api'

import { usePokeQuery } from '@/hooks/convex/use-query'

export const useMeQuery = () => {
  return usePokeQuery(api.public.user.me, {})
}
