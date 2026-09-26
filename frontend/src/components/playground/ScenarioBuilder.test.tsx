import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { expect, test } from 'vitest'
import { type CheckRequestForm, emptyForm } from '@/lib/checkRequestForm'
import { ScenarioBuilder } from './ScenarioBuilder'

function Harness() {
  const [f, setF] = useState<CheckRequestForm>(emptyForm)
  return <ScenarioBuilder value={f} onChange={setF} />
}

test('request type toggle swaps the fields', async () => {
  render(<Harness />)
  expect(screen.getByTestId('tool-call-fields')).toBeInTheDocument()
  await userEvent.click(screen.getByRole('radio', { name: 'External call' }))
  expect(screen.getByTestId('external-call-fields')).toBeInTheDocument()
  expect(screen.queryByTestId('tool-call-fields')).not.toBeInTheDocument()
  expect(screen.getByLabelText('URL')).toBeInTheDocument()
  await userEvent.click(screen.getByRole('radio', { name: 'Content' }))
  expect(screen.getByTestId('content-fields')).toBeInTheDocument()
  expect(screen.queryByLabelText('URL')).not.toBeInTheDocument()
})

test('history rows can be added and removed', async () => {
  render(<Harness />)
  await userEvent.click(screen.getByRole('button', { name: 'Add prior call' }))
  await userEvent.click(screen.getByRole('button', { name: 'Add prior call' }))
  expect(screen.getByTestId('history-1')).toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Remove history 1' }))
  expect(screen.queryByTestId('history-1')).not.toBeInTheDocument()
  expect(screen.getByTestId('history-0')).toBeInTheDocument()
})
