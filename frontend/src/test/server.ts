import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'

export const defaultHandlers = [
  http.get('*/api/health', () => HttpResponse.json({ status: 'ok', version: '0.1.0', jev_configured: true })),
  http.post('*/api/validate/rule-body', () =>
    HttpResponse.json({ valid: true, errors: [], content_hash: 'sha256:abc', jev_model: 'jev-latest', live_problems: [] }),
  ),
]

export const server = setupServer(...defaultHandlers)
