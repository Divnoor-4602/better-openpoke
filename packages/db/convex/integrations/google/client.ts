import { Oauth } from './oauth/oauth'

export class GoogleClient {
  readonly oauth: Oauth

  constructor() {
    this.oauth = new Oauth()
  }
}
