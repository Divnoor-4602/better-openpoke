import { pokeQuery } from '../../auth'
import { vCalendarProvider } from '../../calendar_connection/validators'

export const getCalendarConnection = pokeQuery({
  args: { provider: vCalendarProvider },
  handler: async (ctx, { provider }) => {
    return await ctx.db
      .query('calendarConnections')
      .withIndex('by_user_provider', (q) =>
        q.eq('userId', ctx.user._id).eq('provider', provider),
      )
      .unique()
  },
})
