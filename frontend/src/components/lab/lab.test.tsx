import { act, render, renderHook, screen, within } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { useRunEvents } from '@/api/lab'
import type { DecisionEvent, RunStep } from '@/api/types'
import { mergeSteps } from '@/lib/lab'
import { RunTimeline } from './RunTimeline'

function step(over: Partial<RunStep> = {}): RunStep {
  return {
    index: 1,
    tool: 'read_customer_profile',
    args: { customer_id: 'C-1' },
    reason: 'look up the customer',
    verdict: 'allow',
    result_verdict: null,
    reached_tool: true,
    message: 'ok',
    decisions: [],
    latency_ms: 12,
    expected_verdict: null,
    expected_result_verdict: null,
    expect_reached_tool: null,
    passed: null,
    mismatches: [],
    ...over,
  }
}

function renderTimeline(steps: RunStep[]) {
  const qc = new QueryClient()
  const router = createMemoryRouter(
    [{ path: '/', element: <RunTimeline run={{ id: 'r1', mode: 'scripted', status: 'failed', scenario_id: 'pii' }} steps={steps} rules={{}} onRetry={() => {}} /> }],
  )
  return render(
    <QueryClientProvider client={qc}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
}

test('timeline renders each verdict and whether the call reached the tool', () => {
  renderTimeline([
    step(),
    step({ index: 2, tool: 'http_request', verdict: 'deny', reached_tool: false }),
    step({ index: 3, tool: 'delete_customer', verdict: 'escalate', reached_tool: false }),
  ])
  const s1 = screen.getByTestId('step-1')
  expect(within(s1).getByText('allow')).toBeInTheDocument()
  expect(within(s1).getByTestId('reached')).toBeInTheDocument()
  const s2 = screen.getByTestId('step-2')
  expect(within(s2).getByText('deny')).toBeInTheDocument()
  expect(within(s2).getByTestId('not-reached')).toBeInTheDocument()
  expect(within(s2).queryByRole('button', { name: /retry/i })).toBeNull()
  // only escalated steps can be retried
  expect(within(screen.getByTestId('step-3')).getByRole('button', { name: /retry/i })).toBeInTheDocument()
})

test('scripted steps show expected vs actual, failures highlighted', () => {
  renderTimeline([
    step({ expected_verdict: 'allow', expect_reached_tool: true, passed: true }),
    step({
      index: 2,
      tool: 'http_request',
      verdict: 'allow',
      reached_tool: true,
      expected_verdict: 'deny',
      expect_reached_tool: false,
      passed: false,
      mismatches: ['verdict allow != expected deny'],
    }),
  ])
  expect(screen.getByTestId('step-1')).toHaveAttribute('data-passed', 'true')
  expect(within(screen.getByTestId('step-1')).getByTestId('step-pass')).toBeInTheDocument()
  const failed = screen.getByTestId('step-2')
  expect(failed).toHaveAttribute('data-passed', 'false')
  expect(failed.className).toMatch(/border-red/)
  expect(within(failed).getByTestId('step-expected')).toHaveTextContent('expected deny · must not reach tool')
  expect(within(failed).getByText('verdict allow != expected deny')).toBeInTheDocument()
})

test('Open in Playground appears when the step has a checked request', () => {
  const d: DecisionEvent = {
    id: 'e1',
    session: 'r1',
    step: 1,
    gate: 'tool_call',
    verdict: 'allow',
    forwarded: true,
    check_request: { gate: 'tool_call', request: { kind: 'tool_call', tool: 'read_customer_profile', args: {} } },
    decision: null,
    latency_ms: 1,
  }
  renderTimeline([step({ decisions: [d] })])
  expect(screen.getByRole('button', { name: 'Open in Playground' })).toBeInTheDocument()
})

test('mergeSteps dedupes by index, later sources win', () => {
  const merged = mergeSteps([step(), step({ index: 2 })], [step({ index: 2, verdict: 'deny' })])
  expect(merged.map((s) => [s.index, s.verdict])).toEqual([
    [1, 'allow'],
    [2, 'deny'],
  ])
})

// --- SSE -------------------------------------------------------------------------------

class FakeEventSource {
  static instances: FakeEventSource[] = []
  listeners: Record<string, ((e: MessageEvent) => void)[]> = {}
  closed = false
  url: string
  constructor(url: string) {
    this.url = url
    FakeEventSource.instances.push(this)
  }
  addEventListener(type: string, fn: (e: MessageEvent) => void) {
    ;(this.listeners[type] ??= []).push(fn)
  }
  close() {
    this.closed = true
  }
  emit(type: string, data: unknown) {
    const e = new MessageEvent(type, { data: data === undefined ? undefined : JSON.stringify(data) })
    for (const fn of this.listeners[type] ?? []) fn(e)
  }
}

beforeEach(() => {
  FakeEventSource.instances = []
  vi.stubGlobal('EventSource', FakeEventSource)
})
afterEach(() => vi.unstubAllGlobals())

test('useRunEvents dedupes replayed steps after a reconnect and closes on done', () => {
  const { result } = renderHook(() => useRunEvents('r1'))
  const es = FakeEventSource.instances[0]!
  expect(es.url).toBe('/api/lab/runs/r1/events')
  act(() => {
    es.emit('step', step({ index: 1 }))
    es.emit('step', step({ index: 2, verdict: 'deny' }))
    // a transport error without data is a reconnect, not a failure
    es.emit('error', undefined)
    // on reconnect the server replays what was already sent
    es.emit('step', step({ index: 1 }))
    es.emit('step', step({ index: 2, verdict: 'deny' }))
    es.emit('step', step({ index: 3 }))
  })
  expect(result.current.error).toBeNull()
  expect(result.current.steps.map((s) => s.index)).toEqual([1, 2, 3])
  expect(es.closed).toBe(false)
  act(() => es.emit('done', { id: 'r1', mode: 'scripted', status: 'passed', agent_id: 'a', steps: [] }))
  expect(result.current.done?.status).toBe('passed')
  expect(result.current.steps).toHaveLength(3)
  expect(es.closed).toBe(true)
})

test('useRunEvents surfaces a server error event', () => {
  const { result } = renderHook(() => useRunEvents('missing'))
  act(() => FakeEventSource.instances[0]!.emit('error', { detail: 'run not found on the agent' }))
  expect(result.current.error).toBe('run not found on the agent')
  expect(FakeEventSource.instances[0]!.closed).toBe(true)
})
