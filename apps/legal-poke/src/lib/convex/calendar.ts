import type { TMbListEventsOutput } from '@general-poke/db/types'

import { useConvexAction } from '@convex-dev/react-query'
import { api } from '@general-poke/db/api'
import { useQuery } from '@tanstack/react-query'

import { useConvexAuthGate } from '@/hooks/convex/auth'
import { usePokeAction } from '@/hooks/convex/use-action'
import { usePokeMutation } from '@/hooks/convex/use-mutation'
import { usePokeQuery } from '@/hooks/convex/use-query'

export const useCalendarConnectionQuery = (args: { provider: 'google' }) => {
  return usePokeQuery(api.public.calendar.queries.getCalendarConnection, args)
}

export const useStartGoogleOauthAction = () => {
  return usePokeAction(api.public.calendar.actions.startGoogleOauth)
}

export const useDisconnectCalendarAction = () => {
  return usePokeAction(api.public.calendar.actions.disconnectCalendar)
}

export const useSetAutoJoinMutation = () => {
  return usePokeMutation(api.public.calendar.mutations.setAutoJoin)
}

export const useCalendarEventsQuery = (args: {
  enabled: boolean
  provider: 'google'
}) => {
  useConvexAuthGate()
  const action = useConvexAction(api.public.calendar.actions.listUpcomingEvents)
  return useQuery<TMbListEventsOutput>({
    enabled: args.enabled,
    queryFn: () => action({ provider: args.provider }),
    queryKey: ['calendar-events', args.provider],
  })
}

export const useScheduleBotForEventAction = () => {
  return usePokeAction(api.public.calendar.actions.scheduleBotForEvent)
}

export const useCancelBotForEventAction = () => {
  return usePokeAction(api.public.calendar.actions.cancelBotForEvent)
}
