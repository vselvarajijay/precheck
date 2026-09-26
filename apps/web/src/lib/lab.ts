import type { DecisionEvent, RunStep } from '@/api/types'

export const RUN_STATUS_STYLE: Record<string, string> = {
  running: 'bg-sky-100 text-sky-900 border-sky-200',
  passed: 'bg-emerald-100 text-emerald-800 border-emerald-200',
  completed: 'bg-emerald-100 text-emerald-800 border-emerald-200',
  failed: 'bg-red-100 text-red-800 border-red-200',
  error: 'bg-red-100 text-red-800 border-red-200',
}

/** The tool_call decision for a step (the one a playground re-check starts from). */
export function callDecision(step: RunStep): DecisionEvent | undefined {
  return step.decisions?.find((d) => d.gate === 'tool_call') ?? step.decisions?.[0]
}

/** Union of steps by index; later sources win. */
export function mergeSteps(...sources: (RunStep[] | undefined)[]): RunStep[] {
  const byIndex = new Map<number, RunStep>()
  for (const src of sources) for (const s of src ?? []) byIndex.set(s.index, s)
  return [...byIndex.values()].sort((a, b) => a.index - b.index)
}
