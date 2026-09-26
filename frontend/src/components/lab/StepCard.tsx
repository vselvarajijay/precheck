import { CheckCircle2, CircleSlash, RotateCcw, XCircle } from 'lucide-react'
import { useNavigate } from 'react-router'
import type { RuleInfo, RunStep } from '@/api/types'
import { RuleResultCard } from '@/components/decision/RuleResultCard'
import { SaveTestCase } from '@/components/playground/SaveTestCase'
import { VerdictBadge } from '@/components/rules/badges'
import { Button } from '@/components/ui/button'
import { callDecision } from '@/lib/lab'
import { cn } from '@/lib/utils'

interface Props {
  step: RunStep
  rules: Record<string, RuleInfo>
  onRetry?: (index: number) => void
  retrying?: boolean
}

export function StepCard({ step, rules, onRetry, retrying }: Props) {
  const navigate = useNavigate()
  const scripted = step.passed !== null && step.passed !== undefined
  const call = callDecision(step)
  return (
    <li
      className={cn(
        'space-y-2 rounded-lg border p-3',
        scripted && !step.passed && 'border-red-300 bg-red-50/40',
      )}
      data-testid={`step-${step.index}`}
      data-passed={scripted ? String(step.passed) : undefined}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="text-sm font-medium">
            <span className="text-muted-foreground">#{step.index}</span> <span className="font-mono">{step.tool}</span>
          </div>
          <div className="truncate font-mono text-[11px] text-muted-foreground" title={JSON.stringify(step.args)}>
            {JSON.stringify(step.args)}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {step.verdict ? <VerdictBadge verdict={step.verdict} /> : <span className="text-xs text-muted-foreground">no verdict</span>}
          {step.result_verdict && (
            <span className="flex items-center gap-1 text-xs text-muted-foreground">
              result <VerdictBadge verdict={step.result_verdict} />
            </span>
          )}
          <ReachedTool reached={step.reached_tool} />
          {scripted &&
            (step.passed ? (
              <span className="flex items-center gap-1 text-xs text-emerald-700" data-testid="step-pass">
                <CheckCircle2 className="size-4" aria-hidden /> pass
              </span>
            ) : (
              <span className="flex items-center gap-1 text-xs text-red-700" data-testid="step-fail">
                <XCircle className="size-4" aria-hidden /> fail
              </span>
            ))}
        </div>
      </div>
      {step.reason && <p className="text-xs">Reason: “{step.reason}”</p>}
      {scripted && (
        <div className="text-xs text-muted-foreground" data-testid="step-expected">
          expected <span className="font-mono">{step.expected_verdict}</span>
          {step.expected_result_verdict && <> · result <span className="font-mono">{step.expected_result_verdict}</span></>}
          {' · '}
          {step.expect_reached_tool ? 'reaches tool' : 'must not reach tool'}
          {(step.mismatches?.length ?? 0) > 0 && (
            <ul className="mt-1 list-disc pl-4 text-red-700">
              {step.mismatches?.map((m) => <li key={m}>{m}</li>)}
            </ul>
          )}
        </div>
      )}
      <details className="text-xs">
        <summary className="cursor-pointer text-muted-foreground">
          Details · {step.latency_ms.toFixed(0)} ms · {step.decisions?.length ?? 0} decision(s)
        </summary>
        <div className="mt-2 space-y-2">
          {step.message && <pre className="rounded bg-muted/50 p-2 whitespace-pre-wrap">{step.message}</pre>}
          {step.decisions?.map((d) => (
            <div key={d.id} className="space-y-2">
              <div className="font-mono text-[11px] text-muted-foreground">
                {d.gate} → {d.verdict} {d.forwarded ? '(forwarded)' : '(blocked)'} {d.note && `· ${d.note}`}
              </div>
              {d.decision?.rule_results
                ?.filter((r) => r.matched)
                .map((r) => <RuleResultCard key={r.rule_id} result={r} rule={rules[r.rule_id]} />)}
            </div>
          ))}
          {call?.check_request && call.decision && (
            <SaveTestCase checkRequest={call.check_request} decision={call.decision} rules={rules} />
          )}
        </div>
      </details>
      <div className="flex gap-2">
        {call?.check_request && (
          <Button size="sm" variant="outline" onClick={() => navigate('/playground', { state: { checkRequest: call.check_request } })}>
            Open in Playground
          </Button>
        )}
        {step.verdict === 'escalate' && onRetry && (
          <Button size="sm" variant="outline" onClick={() => onRetry(step.index)} disabled={retrying}>
            <RotateCcw aria-hidden /> Retry
          </Button>
        )}
      </div>
    </li>
  )
}

function ReachedTool({ reached }: { reached: boolean | null | undefined }) {
  if (reached === null || reached === undefined) return null
  return reached ? (
    <span className="text-xs text-emerald-700" data-testid="reached">reached tool</span>
  ) : (
    <span className="flex items-center gap-1 text-xs text-muted-foreground" data-testid="not-reached">
      <CircleSlash className="size-3.5" aria-hidden /> not reached
    </span>
  )
}
