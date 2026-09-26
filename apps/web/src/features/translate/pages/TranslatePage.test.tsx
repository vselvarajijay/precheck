import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { expect, test } from 'vitest'
import type { TranslateResponse } from '@/shared/api/types'
import { renderApp } from '@/test/render'
import { server } from '@/test/server'

const PROV = { translator_model: 'claude-sonnet-5', prompt_version: 'translate_v1+abc', code_version: '0.1.0' }
const USAGE = { input_tokens: 1, output_tokens: 1, cache_creation_input_tokens: 0, cache_read_input_tokens: 0 }

function translated(): TranslateResponse {
  const refundTest = {
    name: 'big refund',
    expected_verdict: 'escalate' as const,
    origin: 'generated' as const,
    check_request: { gate: 'tool_call' as const, request: { kind: 'tool_call' as const, tool: 'issue_refund', args: { amount: 900 } } },
  }
  return {
    business_case_id: 'case-1',
    result: {
      status: 'translated',
      provenance: PROV,
      usage: USAGE,
      cost_usd: 0.0712,
      repair_rounds: 1,
      requirements: [
        { source_sentence: 'Refunds over $500 need a manager.', requirement: 'big refunds need a human', routing: 'deterministic', routing_reason: 'number' },
      ],
      clarifications: [
        { id: 'approval', question: 'Hold for a human or require an approver field?', options: ['hold', 'field'], why: 'no approval signal' },
      ],
      warnings: [],
      errors: [],
      rules: [
        {
          spec: {
            id: 'refund-over-limit',
            name: 'Refund over limit',
            gate: 'tool_call',
            source_text: 'Refunds over $500 need a manager.',
            explanation: 'Big refunds wait for a human.',
            tests: [],
            body: {
              applies_when: { op: 'eq', path: 'request.tool', value: 'issue_refund' },
              requires: ['request.args.amount'],
              on_missing: 'escalate',
              severity: 'medium',
              deterministic: { predicate: { op: 'gt', path: 'request.args.amount', value: 500 }, verdict_when_true: 'escalate' },
            },
          },
          warnings: [],
        },
        {
          spec: {
            id: 'refund-different-card',
            name: 'Refund to different card',
            gate: 'tool_call',
            source_text: 'Never refund to a different card.',
            explanation: 'Refunds go back to the original card.',
            tests: [],
            body: {
              requires: ['history'],
              on_missing: 'escalate',
              severity: 'high',
              jev: {
                model: 'jev-latest',
                state_template: ['request', 'history'],
                questions: { different_method: { type: 'noul', instructions: 'Is the card different?' } },
                outcomes: { different_method: { type: 'noul', bands: { escalate_at: 0.3, deny_at: 0.6 }, direction: 'high_is_bad' } },
              },
            },
          },
          warnings: [{ rule_id: 'refund-different-card', code: 'vague_criteria', message: 'no criteria' }],
        },
      ],
      tests: [
        { rule_id: 'refund-over-limit', kind: 'negative', test: refundTest },
        { rule_id: 'refund-different-card', kind: 'negative', test: { ...refundTest, expected_verdict: 'deny' } },
      ],
    },
  }
}

function streamOf(events: unknown[]) {
  const enc = new TextEncoder()
  return new ReadableStream({
    start(c) {
      for (const e of events) c.enqueue(enc.encode(`${JSON.stringify(e)}\n`))
      c.close()
    },
  })
}

function mockStream(result: TranslateResponse, seen: unknown[] = []) {
  server.use(
    http.post('*/api/translate/stream', async ({ request }) => {
      seen.push(await request.json())
      const events = [
        { type: 'progress', stage: 'plan' },
        { type: 'progress', stage: 'rules' },
        { type: 'progress', stage: 'validating' },
        { type: 'progress', stage: 'repairing' },
        { type: 'progress', stage: 'tests' },
        { type: 'result', data: result },
      ]
      return new HttpResponse(streamOf(events), { headers: { 'content-type': 'application/x-ndjson' } })
    }),
  )
}

async function runTranslation() {
  renderApp('/rules/translate')
  await userEvent.type(screen.getByLabelText('Business case'), 'Refunds over $500 need a manager.')
  await userEvent.selectOptions(screen.getByLabelText('Gate hint'), 'tool_call')
  await userEvent.type(screen.getByLabelText('Tools'), 'issue_refund, lookup_order')
  await userEvent.click(screen.getByRole('button', { name: /Translate/ }))
}

test('translates, shows progress, cards, warnings and clarifications', async () => {
  const seen: unknown[] = []
  mockStream(translated(), seen)
  await runTranslation()
  expect(await screen.findByTestId('translated-rule-refund-over-limit')).toBeInTheDocument()
  expect(seen[0]).toMatchObject({ text: 'Refunds over $500 need a manager.', gate_hint: 'tool_call', tools: ['issue_refund', 'lookup_order'] })
  const progress = screen.getByTestId('progress')
  expect(within(progress).getAllByRole('listitem').map((li) => li.getAttribute('data-state'))).toEqual(['done', 'done', 'done', 'done'])
  expect(progress).toHaveTextContent('(1 repair)')
  expect(screen.getByTestId('translation-meta')).toHaveTextContent('claude-sonnet-5 · translate_v1+abc · $0.0712')
  expect(screen.getByText('request.args.amount > 500 → escalate')).toBeInTheDocument()
  expect(screen.getByTestId('warnings-refund-different-card')).toHaveTextContent('vague_criteria')
  expect(within(screen.getByTestId('clarifications')).getByText('Optional clarifications')).toBeInTheDocument()
})

test('edits and removals flow into the save payload', async () => {
  mockStream(translated())
  let saved: { rules: { id: string; body: { jev?: { questions: Record<string, { instructions: string }>; state_template: string[] } } }[]; tests: { rule_id: string }[] } | null = null
  server.use(
    http.post('*/api/translate/case-1/save', async ({ request }) => {
      saved = (await request.json()) as typeof saved
      return HttpResponse.json({ rules: [{ requested_id: 'refund-different-card', id: 'refund-different-card' }], tests_created: 1 }, { status: 201 })
    }),
    http.get('*/api/rules', () => HttpResponse.json([])),
  )
  await runTranslation()
  await screen.findByTestId('translated-rule-refund-different-card')
  const q = screen.getByLabelText('refund-different-card question different_method')
  await userEvent.clear(q)
  await userEvent.type(q, 'Does the refund go to another card?')
  await userEvent.click(screen.getByRole('checkbox', { name: 'refund-different-card looks at reason' }))
  await userEvent.click(screen.getByRole('button', { name: 'Remove refund-over-limit' }))
  await userEvent.click(screen.getByRole('button', { name: 'Save all as draft' }))
  await waitFor(() => expect(saved).not.toBeNull())
  expect(saved!.rules.map((r) => r.id)).toEqual(['refund-different-card'])
  expect(saved!.rules[0]!.body.jev!.questions.different_method!.instructions).toBe('Does the refund go to another card?')
  expect(saved!.rules[0]!.body.jev!.state_template).toEqual(['request', 'history', 'reason'])
  expect(saved!.tests.map((t) => t.rule_id)).toEqual(['refund-different-card'])
  expect(await screen.findByRole('heading', { name: 'Rules' })).toBeInTheDocument()
})

test('blocking clarifications are answered and re-translated', async () => {
  const blocked = translated()
  blocked.result = { ...blocked.result, status: 'needs_clarification', rules: [], tests: [] }
  mockStream(blocked)
  let answers: unknown = null
  server.use(
    http.post('*/api/translate/case-1/answers', async ({ request }) => {
      answers = await request.json()
      return HttpResponse.json(translated())
    }),
  )
  await runTranslation()
  const panel = await screen.findByTestId('clarifications')
  expect(within(panel).getByText('Clarifications needed')).toBeInTheDocument()
  const submit = within(panel).getByRole('button', { name: 'Re-translate with answers' })
  expect(submit).toBeDisabled()
  await userEvent.click(within(panel).getByRole('radio', { name: 'hold' }))
  await userEvent.click(submit)
  await waitFor(() => expect(answers).toEqual({ answers: { approval: 'hold' } }))
  expect(await screen.findByTestId('translated-rule-refund-over-limit')).toBeInTheDocument()
})

test('stream errors are shown', async () => {
  server.use(
    http.post('*/api/translate/stream', () =>
      new HttpResponse(streamOf([{ type: 'progress', stage: 'plan' }, { type: 'error', status: 503, detail: 'rate limit' }]), {
        headers: { 'content-type': 'application/x-ndjson' },
      }),
    ),
  )
  await runTranslation()
  expect(await screen.findByText('Translation failed')).toBeInTheDocument()
})
