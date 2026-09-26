import { screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { expect, test } from 'vitest'
import { NAV_ITEMS } from '@/components/layout/AppShell'
import { renderApp } from '@/test/render'
import { server } from '@/test/server'


test('renders nav links and redirects / to Rules', async () => {
  server.use(http.get('*/api/rules', () => HttpResponse.json([])))
  renderApp('/')
  for (const item of NAV_ITEMS) {
    expect(screen.getByRole('link', { name: item.label })).toHaveAttribute('href', item.to)
  }
  expect(await screen.findByRole('heading', { name: 'Rules' })).toBeInTheDocument()
})

test('health badge shows API ok and Jev configured', async () => {
  server.use(http.get('*/api/rules', () => HttpResponse.json([])))
  renderApp('/')
  expect(await screen.findByText('API ok · Jev configured')).toBeInTheDocument()
})

test('health badge shows API down on error', async () => {
  server.use(
    http.get('*/api/health', () => new HttpResponse(null, { status: 500 })),
    http.get('*/api/rules', () => HttpResponse.json([])),
  )
  renderApp('/')
  expect(await screen.findByText('API down', {}, { timeout: 3000 })).toBeInTheDocument()
})
