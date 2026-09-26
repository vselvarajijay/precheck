import type { QuestionResult, RuleInfo, RuleResult } from '@/api/types'
import { VerdictBadge } from '@/components/rules/badges'
import { describePredicate } from '@/lib/ruleBody'
import { ProbabilityBar } from './ProbabilityBar'

const SOURCE_LABEL: Record<string, string> = {
  missing_fields: 'missing fields',
  deterministic: 'code',
  jev: 'jev',
  error: 'jev error',
  no_verdict: 'skipped',
}

export function RuleResultCard({ result, rule }: { result: RuleResult; rule?: RuleInfo }) {
  const body = rule?.body
  return (
    <div className="space-y-2 rounded-lg border p-3" data-testid={`rule-result-${result.rule_id}`}>
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="text-sm font-medium">{rule?.name ?? result.rule_id}</div>
          <div className="font-mono text-[11px] text-muted-foreground">
            {result.rule_id} v{result.rule_version ?? '?'} · {SOURCE_LABEL[result.source ?? ''] ?? result.source}
          </div>
        </div>
        {result.verdict ? <VerdictBadge verdict={result.verdict} /> : <span className="text-xs text-muted-foreground">no verdict</span>}
      </div>
      {result.reason && <p className="text-xs text-muted-foreground">{result.reason}</p>}
      {(result.missing_fields?.length ?? 0) > 0 && (
        <p className="text-xs">
          Missing: <span className="font-mono">{result.missing_fields?.join(', ')}</span>
        </p>
      )}
      {result.predicate_result !== null && result.predicate_result !== undefined && body?.deterministic && (
        <div className="rounded bg-muted/50 p-2 font-mono text-xs">
          code: {describePredicate(body.deterministic.predicate)} = {String(result.predicate_result)}
          {Object.keys(result.predicate_inputs ?? {}).length > 0 && (
            <div className="text-muted-foreground">inputs: {JSON.stringify(result.predicate_inputs)}</div>
          )}
        </div>
      )}
      {Object.entries(result.jev ?? {}).map(([qid, q]) => (
        <QuestionRow key={qid} qid={qid} q={q} rule={rule} />
      ))}
      {result.error && <p className="text-xs text-destructive">Error: {result.error}</p>}
    </div>
  )
}

function QuestionRow({ qid, q, rule }: { qid: string; q: QuestionResult; rule?: RuleInfo }) {
  const question = rule?.body.jev?.questions[qid]
  const outcome = rule?.body.jev?.outcomes[qid]
  const answer = q.answer
  return (
    <div className="space-y-1">
      <div className="text-xs">
        <span className="font-mono">{qid}</span>
        {question && <span className="text-muted-foreground"> — {question.instructions}</span>}
      </div>
      {answer.type === 'noul' && outcome?.type === 'noul' && (
        <ProbabilityBar
          value={q.value}
          bands={outcome.bands}
          label={outcome.direction === 'low_is_bad' ? '1−p' : 'p'}
        />
      )}
      {answer.type === 'score' && outcome?.type === 'score' && question?.type === 'score' && (
        <ProbabilityBar value={q.value} bands={outcome.bands} min={0} max={question.criteria.length - 1} label="score" />
      )}
      {answer.type === 'choice' && (
        <div className="text-xs">
          chose <span className="font-mono">{answer.choice}</span> (confidence {answer.confidence.toFixed(2)})
        </div>
      )}
      <div className="text-[11px] text-muted-foreground">band: {q.band} → {q.verdict}</div>
    </div>
  )
}
