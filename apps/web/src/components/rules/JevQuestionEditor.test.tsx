import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { expect, test } from 'vitest'
import type { JevQuestion } from '@/api/types'
import { JevQuestionEditor } from './JevQuestionEditor'

function Harness({ initial }: { initial: JevQuestion }) {
  const [q, setQ] = useState(initial)
  return (
    <>
      <JevQuestionEditor qid="q1" value={q} onChange={setQ} />
      <output data-testid="count">{q.type === 'choice' ? Object.keys(q.criteria).length : q.type === 'score' ? q.criteria.length : 0}</output>
    </>
  )
}

const choice = (n: number): JevQuestion => ({
  type: 'choice',
  instructions: 'Pick',
  criteria: Object.fromEntries(Array.from({ length: n }, (_, i) => [`o${i}`, `option ${i}`])),
})

test('choice: 256th option is blocked with a message', async () => {
  render(<Harness initial={choice(254)} />)
  const add = screen.getByRole('button', { name: 'Add option' })
  await userEvent.click(add)
  expect(screen.getByTestId('count')).toHaveTextContent('255')
  expect(add).toBeDisabled()
  expect(screen.getByText(/at most 255 options/)).toBeInTheDocument()
  await userEvent.click(add)
  expect(screen.getByTestId('count')).toHaveTextContent('255')
})

test('choice: the last option cannot be removed', () => {
  render(<Harness initial={choice(1)} />)
  expect(screen.getByRole('button', { name: 'Remove option 1' })).toBeDisabled()
})

test('score: 11th level is blocked; below 2 levels cannot be removed', async () => {
  const levels = Array.from({ length: 9 }, (_, i) => `level ${i}`)
  render(<Harness initial={{ type: 'score', instructions: 'Risk?', criteria: levels }} />)
  const add = screen.getByRole('button', { name: 'Add level' })
  await userEvent.click(add)
  expect(screen.getByTestId('count')).toHaveTextContent('10')
  expect(add).toBeDisabled()
  expect(screen.getByText(/at most 10 levels/)).toBeInTheDocument()
})

test('score: minimum of 2 levels', () => {
  render(<Harness initial={{ type: 'score', instructions: 'Risk?', criteria: ['low', 'high'] }} />)
  expect(screen.getByRole('button', { name: 'Remove level 0' })).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Remove level 1' })).toBeDisabled()
})

test('switching type keeps the instructions', async () => {
  render(<Harness initial={{ type: 'noul', instructions: 'Keep me?' }} />)
  await userEvent.selectOptions(screen.getByLabelText('Question q1 type'), 'score')
  expect(screen.getByLabelText('Question q1 instructions')).toHaveValue('Keep me?')
  expect(screen.getByTestId('score-criteria')).toBeInTheDocument()
})
