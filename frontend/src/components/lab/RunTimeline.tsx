import type { LabRun, RuleInfo, RunStep } from '@/api/types'
import { Badge } from '@/components/ui/badge'
import { RUN_STATUS_STYLE } from '@/lib/lab'
import { StepCard } from './StepCard'

interface Props {
  run: Pick<LabRun, 'id' | 'mode' | 'status' | 'scenario_id' | 'goal' | 'error' | 'final_text'> | null
  steps: RunStep[]
  rules: Record<string, RuleInfo>
  onRetry?: (index: number) => void
  retrying?: boolean
}

export function RunTimeline({ run, steps, rules, onRetry, retrying }: Props) {
  if (!run) return null
  return (
    <section className="space-y-3" aria-label="Run timeline" data-testid="run-timeline">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="font-medium">{run.scenario_id ?? 'LLM run'}</span>
        <Badge variant="outline" className={RUN_STATUS_STYLE[run.status]} data-testid="run-status">
          {run.status}
        </Badge>
        <span className="font-mono text-[11px] text-muted-foreground">{run.id}</span>
      </div>
      {run.goal && <p className="text-xs text-muted-foreground">Goal: {run.goal}</p>}
      {run.error && <p className="text-xs text-destructive">Error: {run.error}</p>}
      {steps.length === 0 && run.status === 'running' && <p className="text-xs text-muted-foreground">Waiting for the first step…</p>}
      <ol className="space-y-2">
        {steps.map((s) => (
          <StepCard key={s.index} step={s} rules={rules} onRetry={onRetry} retrying={retrying} />
        ))}
      </ol>
      {run.final_text && (
        <div className="rounded-lg border bg-muted/30 p-3 text-sm" data-testid="final-text">
          <div className="mb-1 text-xs font-medium text-muted-foreground">Agent's final reply</div>
          <p className="whitespace-pre-wrap">{run.final_text}</p>
        </div>
      )}
    </section>
  )
}
