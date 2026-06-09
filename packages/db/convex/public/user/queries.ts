import { pokeQuery } from '../../auth'

export const me = pokeQuery({
  args: {},
  handler: (ctx) => ctx.user,
})
