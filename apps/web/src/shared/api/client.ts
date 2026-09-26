import createClient from 'openapi-fetch'
import type { paths } from './schema'

// Same-origin: Vite proxies /api to the backend in dev. `fetch` is resolved per call so
// test interceptors (MSW) installed after import still apply.
export const api = createClient<paths>({
  baseUrl: globalThis.location?.origin ?? '',
  fetch: (request) => globalThis.fetch(request),
})
