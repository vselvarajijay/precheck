import { render, screen } from '@testing-library/react'
import { expect, test } from 'vitest'
import { bandFor, ProbabilityBar } from './ProbabilityBar'

const bands = { escalate_at: 0.4, deny_at: 0.7 }

test.each([
  [0, 'allow', '0%'],
  [0.39, 'allow', '39%'],
  [0.4, 'escalate', '40%'],
  [0.69, 'escalate', '69%'],
  [0.7, 'deny', '70%'],
  [1, 'deny', '100%'],
])('ProbabilityBar value %s -> %s region, marker at %s', (value, region, left) => {
  render(<ProbabilityBar value={value} bands={bands} />)
  const bar = screen.getByTestId('probability-bar')
  expect(bar).toHaveAttribute('data-region', region)
  const marker = bar.querySelector('[data-part="marker"]') as HTMLElement
  expect(Number.parseFloat(marker.style.left)).toBeCloseTo(Number.parseFloat(left), 5)
  expect(screen.getByRole('meter')).toHaveAccessibleName(`p ${value.toFixed(2)} in ${region} band`)
})

test('ProbabilityBar band regions are sized from the thresholds', () => {
  render(<ProbabilityBar value={0.5} bands={bands} />)
  const bar = screen.getByTestId('probability-bar')
  const part = (name: string) => bar.querySelector(`[data-part="${name}"]`) as HTMLElement
  expect(Number.parseFloat(part('allow').style.width)).toBeCloseTo(40, 5)
  expect(Number.parseFloat(part('escalate').style.left)).toBeCloseTo(40, 5)
  expect(Number.parseFloat(part('escalate').style.width)).toBeCloseTo(30, 5)
  expect(Number.parseFloat(part('deny').style.left)).toBeCloseTo(70, 5)
})

test('ProbabilityBar score scale maps onto [min, max]', () => {
  render(<ProbabilityBar value={3} bands={{ escalate_at: 2, deny_at: 3 }} min={0} max={4} label="score" />)
  const bar = screen.getByTestId('probability-bar')
  expect(bar).toHaveAttribute('data-region', 'deny')
  expect(Number.parseFloat((bar.querySelector('[data-part="marker"]') as HTMLElement).style.left)).toBeCloseTo(75, 5)
})

test('bandFor matches the engine: inclusive thresholds; equal thresholds skip escalate', () => {
  expect(bandFor(0.5, { escalate_at: 0.5, deny_at: 0.5 })).toBe('deny')
  expect(bandFor(0.49, { escalate_at: 0.5, deny_at: 0.5 })).toBe('allow')
})
