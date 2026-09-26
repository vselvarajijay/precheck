import { fireEvent, render, screen } from '@testing-library/react'
import { expect, test } from 'vitest'
import { CalibrationHistogram } from './CalibrationHistogram'

const points = [
  { value: 0.03, expected: 'allow' as const },
  { value: 0.04, expected: 'allow' as const },
  { value: 0.55, expected: 'escalate' as const },
  { value: 0.96, expected: 'deny' as const },
]

test('bins answers by expected verdict with a legend and a per-bin tooltip', () => {
  const { container } = render(
    <CalibrationHistogram points={points} range={[0, 1]} current={{ escalate_at: 0.4, deny_at: 0.7 }} suggested={{ escalate_at: 0.3, deny_at: 0.8 }} />,
  )
  const fills = [...container.querySelectorAll('rect[rx="2"]')].map((r) => r.getAttribute('fill'))
  expect(fills).toEqual(['#0d9488', '#d97706', '#be123c'])
  expect(screen.getByText('expected allow')).toBeInTheDocument()
  expect(screen.getByText(/suggested escalate 0.3/)).toBeInTheDocument()
  expect(screen.getByText(/suggested deny 0.8/)).toBeInTheDocument()
  const hitTargets = container.querySelectorAll('rect[fill="transparent"]')
  expect(hitTargets).toHaveLength(20)
  fireEvent.mouseEnter(hitTargets[0]!)
  expect(screen.getByRole('status')).toHaveTextContent('0–0.05: 2 allow · 0 escalate · 0 deny')
})

test('equal suggested thresholds show one label', () => {
  render(<CalibrationHistogram points={points} range={[0, 1]} current={{ escalate_at: 0.4, deny_at: 0.7 }} suggested={{ escalate_at: 0.5, deny_at: 0.5 }} />)
  expect(screen.getByText(/suggested escalate = deny 0.5/)).toBeInTheDocument()
})
