import { expect, test } from 'vitest'
import type { CheckRequest } from '@/api/types'
import { emptyForm, formFromRequest, requestFromForm } from './checkRequestForm'

const CR: CheckRequest = {
  gate: 'tool_call',
  agent: { id: 'support-bot', purpose: 'Support' },
  context: { user_goal: 'Refund #1' },
  history: [{ tool: 'lookup_order', args: { order_id: '1' }, result_summary: 'Visa 4242' }],
  request: { kind: 'tool_call', tool: 'issue_refund', args: { amount: 620 } },
  reason: 'asked',
}

test('form <-> check request round trip', () => {
  expect(requestFromForm(formFromRequest(CR))).toEqual({ request: CR, errors: [] })
})

test('blank optional fields are omitted and errors reported', () => {
  const f = { ...emptyForm(), agentId: '', purpose: '', tool: '', argsText: '{bad' }
  const { request, errors } = requestFromForm(f)
  expect(request).toBeNull()
  expect(errors).toContain('Tool name is required')
  expect(errors.some((e) => e.startsWith('Args:'))).toBe(true)
  const ok = requestFromForm({ ...f, tool: 'x', argsText: '' })
  expect(ok.request).toMatchObject({ agent: null, context: null, history: null, reason: null })
})

test('external call and content kinds', () => {
  const ext = requestFromForm({ ...emptyForm(), kind: 'external_call', url: 'https://x.test', bodyText: 'hi' })
  expect(ext.request?.request).toEqual({ kind: 'external_call', method: 'POST', url: 'https://x.test', body: 'hi' })
  expect(requestFromForm({ ...emptyForm(), kind: 'content' }).errors).toEqual(['Content text is required'])
})
