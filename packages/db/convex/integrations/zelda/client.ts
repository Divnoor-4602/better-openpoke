import { validationError } from '../../error'
import { Sessions } from './sessions/sessions'

type Method = 'DELETE' | 'GET' | 'POST' | 'PUT'

export class ZeldaClient {
  readonly sessions: Sessions
  private readonly baseUrl: string

  constructor(opts: { baseUrl?: string } = {}) {
    const baseUrl = opts.baseUrl ?? process.env.ZELDA_PUBLIC_URL
    if (!baseUrl) {
      validationError({
        entity: 'ZeldaClient',
        message: 'ZELDA_PUBLIC_URL is not set',
      })
    }
    this.baseUrl = baseUrl.replace(/\/$/, '')
    this.sessions = new Sessions(this)
  }

  delete(path: string, token: string): Promise<Response> {
    return this.send('DELETE', path, token)
  }

  get(path: string, token: string): Promise<Response> {
    return this.send('GET', path, token)
  }

  post(path: string, token: string, body?: unknown): Promise<Response> {
    return this.send('POST', path, token, body)
  }

  put(path: string, token: string, body?: unknown): Promise<Response> {
    return this.send('PUT', path, token, body)
  }

  private async send(
    method: Method,
    path: string,
    token: string,
    body?: unknown,
  ): Promise<Response> {
    return await fetch(`${this.baseUrl}${path}`, {
      body: body ? JSON.stringify(body) : undefined,
      headers: {
        authorization: `Bearer ${token}`,
        ...(body ? { 'content-type': 'application/json' } : {}),
      },
      method,
    })
  }
}
