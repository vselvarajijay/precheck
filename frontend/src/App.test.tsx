import { screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { afterAll, afterEach, beforeAll, expect, test } from 'vitest'
import { NAV_ITEMS } from '@/components/layout/AppShell'
import { renderApp } from '@/test/render'

const server = setupServer(
  http.get('*/api/health', () =>
    HttpResponse.json({ status: 'ok', version: '0.1.0', jev_configured: true }),
  ),
)
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

test('renders nav links and redirects / to Rules', async () => {
  renderApp('/')
  for (const item of NAV_ITEMS) {
    expect(screen.getByRole('link', { name: item.label })).toHaveAttribute('href', item.to)
  }
  expect(await screen.findByRole('heading', { name: 'Rules' })).toBeInTheDocument()
})

test('health badge shows API ok and Jev configured', async () => {
  renderApp('/')
  expect(await screen.findByText('API ok · Jev configured')).toBeInTheDocument()
})

test('health badge shows API down on error', async () => {
  server.use(http.get('*/api/health', () => new HttpResponse(null, { status: 500 })))
  renderApp('/')
  expect(await screen.findByText('API down', {}, { timeout: 3000 })).toBeInTheDocument()
})
