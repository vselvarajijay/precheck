import { fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'
import { expect, test } from 'vitest'
import type { Bands } from '@/shared/api/types'
import { BandsSlider } from './BandsSlider'

function Harness({ initial, onValue }: { initial: Bands; onValue?: (b: Bands) => void }) {
  const [b, setB] = useState(initial)
  return (
    <BandsSlider
      value={b}
      onChange={(next) => {
        setB(next)
        onValue?.(next)
      }}
    />
  )
}

test('escalate threshold cannot be set above deny via input', () => {
  const seen: Bands[] = []
  render(<Harness initial={{ escalate_at: 0.4, deny_at: 0.7 }} onValue={(b) => seen.push(b)} />)
  fireEvent.change(screen.getByLabelText('Escalate at'), { target: { value: '0.9' } })
  expect(seen.at(-1)).toEqual({ escalate_at: 0.7, deny_at: 0.7 })
  expect(screen.getByLabelText('Escalate at')).toHaveValue(0.7)
})

test('deny threshold cannot be set below escalate via input', () => {
  const seen: Bands[] = []
  render(<Harness initial={{ escalate_at: 0.4, deny_at: 0.7 }} onValue={(b) => seen.push(b)} />)
  fireEvent.change(screen.getByLabelText('Deny at'), { target: { value: '0.1' } })
  expect(seen.at(-1)).toEqual({ escalate_at: 0.4, deny_at: 0.4 })
})

test('keyboard: escalate thumb stops at the deny thumb', () => {
  render(<Harness initial={{ escalate_at: 0.68, deny_at: 0.7 }} />)
  const escalateThumb = screen.getByRole('slider', { name: 'Escalate threshold' })
  const denyThumb = screen.getByRole('slider', { name: 'Deny threshold' })
  for (let i = 0; i < 10; i++) fireEvent.keyDown(escalateThumb, { key: 'ArrowRight' })
  expect(escalateThumb).toHaveAttribute('aria-valuenow', '0.7')
  expect(denyThumb).toHaveAttribute('aria-valuenow', '0.7')
  fireEvent.keyDown(escalateThumb, { key: 'End' })
  expect(escalateThumb).toHaveAttribute('aria-valuenow', '0.7')
  // and deny cannot go below escalate
  fireEvent.keyDown(denyThumb, { key: 'Home' })
  expect(denyThumb).toHaveAttribute('aria-valuenow', '0.7')
  fireEvent.keyDown(escalateThumb, { key: 'PageDown' })
  expect(escalateThumb).toHaveAttribute('aria-valuenow', '0.6')
})

test('values are rounded to the step (no float noise)', () => {
  const seen: Bands[] = []
  render(<Harness initial={{ escalate_at: 0.4, deny_at: 0.7 }} onValue={(b) => seen.push(b)} />)
  fireEvent.keyDown(screen.getByRole('slider', { name: 'Escalate threshold' }), { key: 'ArrowRight' })
  expect(seen.at(-1)?.escalate_at).toBe(0.41)
})

test('dragging the escalate thumb past deny stops at deny', () => {
  render(<Harness initial={{ escalate_at: 0.2, deny_at: 0.5 }} />)
  const track = screen.getByTestId('bands-slider').firstElementChild as HTMLElement
  track.getBoundingClientRect = () => ({ left: 0, width: 100, top: 0, height: 10, right: 100, bottom: 10, x: 0, y: 0, toJSON: () => ({}) })
  const escalateThumb = screen.getByRole('slider', { name: 'Escalate threshold' })
  fireEvent.pointerDown(escalateThumb, { pointerId: 1, clientX: 20 })
  fireEvent.pointerMove(escalateThumb, { pointerId: 1, clientX: 90 })
  fireEvent.pointerUp(escalateThumb, { pointerId: 1 })
  expect(escalateThumb).toHaveAttribute('aria-valuenow', '0.5')
  expect(screen.getByRole('slider', { name: 'Deny threshold' })).toHaveAttribute('aria-valuenow', '0.5')
})
