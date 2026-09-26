import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { useState } from 'react'
import { expect, test } from 'vitest'
import type { RuleBody } from '@/api/types'
import { server } from '@/test/server'
import { emptyBody } from '@/lib/ruleBody'
import { RuleBodyEditor } from './RuleBodyEditor'

let latest: RuleBody | null = null

function Harness({ initial = emptyBody() }: { initial?: RuleBody }) {
  const [body, setBody] = useState(initial)
  latest = body
  return <RuleBodyEditor value={body} onChange={setBody} />
}

test('form edits are reflected in the JSON tab', async () => {
  render(<Harness />)
  await userEvent.type(screen.getByLabelText('Question q1 instructions'), 'Is it risky?')
  await userEvent.click(screen.getByRole('switch', { name: 'Use a deterministic check' }))
  expect(latest?.deterministic?.predicate).toEqual({ op: 'gt', path: 'request.args.amount', value: 0 })
  await userEvent.click(screen.getByRole('tab', { name: 'JSON' }))
  const editor = await screen.findByTestId('json-editor')
  await waitFor(() => expect(editor).toHaveTextContent('"instructions": "Is it risky?"'))
  expect(editor).toHaveTextContent('"verdict_when_true": "escalate"')
})

test('JSON reflects the form and the form survives a round trip through the tabs', async () => {
  const initial: RuleBody = {
    ...emptyBody(),
    severity: 'high',
    applies_when: { op: 'eq', path: 'request.tool', value: 'issue_refund' },
  }
  render(<Harness initial={initial} />)
  await userEvent.click(screen.getByRole('tab', { name: 'JSON' }))
  const editor = await screen.findByTestId('json-editor')
  expect(editor).toHaveTextContent('"value": "issue_refund"')
  await userEvent.click(screen.getByRole('tab', { name: 'Form' }))
  expect(screen.getByLabelText('Severity')).toHaveValue('high')
  expect(screen.getByLabelText('Applies when value')).toHaveValue('issue_refund')
  expect(latest).toEqual(initial)
})

test('server validation errors are shown inline next to the field', async () => {
  server.use(
    http.post('*/api/validate/rule-body', () =>
      HttpResponse.json({
        valid: false,
        errors: [{ field: 'jev.questions.q1.instructions', message: 'String should have at least 1 character' }],
        live_problems: [],
      }),
    ),
  )
  render(<Harness />)
  const q = screen.getByTestId('question-q1')
  expect(await within(q).findByText('String should have at least 1 character')).toBeInTheDocument()
  expect(within(q).getByText('Instructions are required.')).toBeInTheDocument()
})

test('renaming a question keeps its outcome', async () => {
  render(<Harness />)
  const id = screen.getByLabelText('Question id q1')
  await userEvent.clear(id)
  await userEvent.type(id, 'different_method')
  await userEvent.tab()
  expect(Object.keys(latest!.jev!.questions)).toEqual(['different_method'])
  expect(Object.keys(latest!.jev!.outcomes)).toEqual(['different_method'])
})

test('choice outcome map follows the options', async () => {
  render(<Harness />)
  await userEvent.selectOptions(screen.getByLabelText('Question q1 type'), 'choice')
  await userEvent.click(screen.getByRole('button', { name: 'Add option' }))
  const outcome = latest!.jev!.outcomes.q1!
  expect(outcome.type).toBe('choice')
  expect(outcome.type === 'choice' && Object.keys(outcome.map)).toEqual(['option_a', 'option_b', 'option_3'])
  await userEvent.selectOptions(screen.getByLabelText('Verdict for option_3'), 'deny')
  const o2 = latest!.jev!.outcomes.q1!
  expect(o2.type === 'choice' && o2.map.option_3).toBe('deny')
})
