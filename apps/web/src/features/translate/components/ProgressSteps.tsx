import { CheckIcon, LoaderCircleIcon } from 'lucide-react'
import type { TranslateStage } from '@/features/translate/api'
import { cn } from '@/shared/lib/utils'

const STEPS: { key: string; label: string; stages: TranslateStage[] }[] = [
  { key: 'plan', label: 'Decomposing and classifying', stages: ['plan'] },
  { key: 'rules', label: 'Generating rules', stages: ['rules'] },
  { key: 'validate', label: 'Validating', stages: ['validating', 'repairing'] },
  { key: 'tests', label: 'Generating tests', stages: ['tests'] },
]

/** Live pipeline progress from the NDJSON stream. `stage` null = not started / finished. */
export function ProgressSteps({ stage, repairs, done }: { stage: TranslateStage | null; repairs: number; done: boolean }) {
  const current = STEPS.findIndex((s) => stage && s.stages.includes(stage))
  return (
    <ol className="flex flex-wrap gap-4 text-sm" aria-label="Translation progress" data-testid="progress">
      {STEPS.map((s, i) => {
        const state = done || i < current ? 'done' : i === current ? 'active' : 'pending'
        return (
          <li key={s.key} className={cn('flex items-center gap-1.5', state === 'pending' && 'text-muted-foreground')} data-state={state}>
            {state === 'done' && <CheckIcon className="size-4 text-emerald-600" />}
            {state === 'active' && <LoaderCircleIcon className="size-4 animate-spin" />}
            {state === 'pending' && <span className="size-4 rounded-full border" />}
            {s.label}
            {s.key === 'validate' && repairs > 0 && <span className="text-xs text-amber-700">({repairs} repair{repairs > 1 ? 's' : ''})</span>}
          </li>
        )
      })}
    </ol>
  )
}
