import type { Decision, RuleInfo } from '@/shared/api/types'
import { VerdictBadge } from './badges'
import { RuleResultCard } from './RuleResultCard'

export function DecisionPanel({ decision, rules }: { decision: Decision; rules: Record<string, RuleInfo> }) {
  const results = decision.rule_results ?? []
  const matched = results.filter((r) => r.matched)
  const unmatched = results.filter((r) => !r.matched)
  return (
    <div className="space-y-3" data-testid="decision-panel">
      <div className="flex items-center justify-between gap-2">
        <div className="text-sm font-semibold">Decision</div>
        <VerdictBadge verdict={decision.verdict} className="px-3 py-1 text-sm" />
      </div>
      <div className="text-xs text-muted-foreground" data-testid="decision-summary">
        {matched.length} rule{matched.length === 1 ? '' : 's'} matched · {decision.latency_ms.toFixed(0)} ms ·{' '}
        {(decision.usage?.input_tokens ?? 0).toLocaleString()} tok
        {decision.gate_default_applied && ' · no rule decided: gate default applied'}
      </div>
      {matched.map((r) => (
        <RuleResultCard key={r.rule_id} result={r} rule={rules[r.rule_id]} />
      ))}
      {unmatched.length > 0 && (
        <details className="text-xs text-muted-foreground">
          <summary className="cursor-pointer">{unmatched.length} rule(s) did not apply</summary>
          <ul className="mt-1 space-y-0.5">
            {unmatched.map((r) => (
              <li key={r.rule_id}>
                <span className="font-mono">{r.rule_id}</span>: {r.reason}
              </li>
            ))}
          </ul>
        </details>
      )}
      <div className="text-[11px] text-muted-foreground">
        Final: deny &gt; escalate &gt; allow · engine {decision.versions.engine} · jev {decision.versions.jev_model ?? '—'} · rules{' '}
        {Object.entries(decision.versions.rules ?? {})
          .map(([id, v]) => `${id}@v${v}`)
          .join(', ') || '—'}
      </div>
    </div>
  )
}
