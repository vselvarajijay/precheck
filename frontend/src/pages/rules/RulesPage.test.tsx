import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { expect, test } from 'vitest'
import { ruleSummary } from '@/test/fixtures'
import { renderApp } from '@/test/render'
import { server } from '@/test/server'

const RULES = [
  ruleSummary(),
  ruleSummary({
    id: 'pii-egress',
    name: 'No PII to external domains',
    gate: 'egress',
    status: 'draft',
    has_deterministic: true,
    has_jev: true,
    jev_model: 'jev-latest',
    created_by: 'agent',
    applies_to_tools: [],
  }),
]

function mockRules() {
  const seen: URLSearchParams[] = []
  server.use(
    http.get('*/api/rules', ({ request }) => {
      const params = new URL(request.url).searchParams
      seen.push(params)
      const gate = params.get('gate')
      const q = params.get('q')?.toLowerCase()
      return HttpResponse.json(
        RULES.filter((r) => (!gate || r.gate === gate) && (!q || r.name.toLowerCase().includes(q))),
      )
    }),
  )
  return seen
}

test('lists rules with badges', async () => {
  mockRules()
  renderApp('/rules')
  const row = await screen.findByTestId('rule-row-pii-egress')
  expect(within(row).getByText('egress')).toBeInTheDocument()
  expect(within(row).getByText('code')).toBeInTheDocument()
  expect(within(row).getByText('jev')).toBeInTheDocument()
  expect(within(row).getByText('proposed by agent')).toBeInTheDocument()
  expect(within(row).getByText('○ draft')).toBeInTheDocument()
  const live = screen.getByTestId('rule-row-refund-over-limit')
  expect(within(live).getByText('● live')).toBeInTheDocument()
  expect(within(live).getByText('issue_refund')).toBeInTheDocument()
})

test('search and gate filters are sent to the API', async () => {
  const seen = mockRules()
  renderApp('/rules')
  await screen.findByTestId('rule-row-pii-egress')
  await userEvent.type(screen.getByLabelText('Search rules'), 'pii')
  await waitFor(() => expect(screen.queryByTestId('rule-row-refund-over-limit')).not.toBeInTheDocument())
  expect(seen.at(-1)?.get('q')).toBe('pii')

  await userEvent.clear(screen.getByLabelText('Search rules'))
  expect(await screen.findByTestId('rule-row-refund-over-limit')).toBeInTheDocument()
  await userEvent.selectOptions(screen.getByLabelText('Filter by gate'), 'tool_call')
  await waitFor(() => expect(screen.queryByTestId('rule-row-pii-egress')).not.toBeInTheDocument())
  expect(seen.at(-1)?.get('gate')).toBe('tool_call')
  expect(screen.getByTestId('rule-row-refund-over-limit')).toBeInTheDocument()

  await userEvent.selectOptions(screen.getByLabelText('Filter by status'), 'archived')
  await waitFor(() => expect(seen.at(-1)?.get('status')).toBe('archived'))
})

test('empty state', async () => {
  server.use(http.get('*/api/rules', () => HttpResponse.json([])))
  renderApp('/rules')
  expect(await screen.findByText(/No rules match/)).toBeInTheDocument()
})
