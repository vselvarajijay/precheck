import { PlayIcon, SparklesIcon, Trash2Icon } from 'lucide-react'
import { Fragment, useState } from 'react'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { useRuleTestCases } from '@/features/playground/api'
import { ApiError } from '@/shared/api/problem'
import { useApplyBands, useCalibrate, useDeleteTestCase, useGenerateTests, useRunTests, useTestRun, useTestRuns } from '@/features/tests/api'
import type { CalibrationResult, RuleDetail } from '@/shared/api/types'
import { VerdictBadge } from '@/shared/decision/badges'
import { Button } from '@/shared/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/shared/ui/table'
import { NativeSelect } from '@/shared/ui/native-select'
import { CalibrationHistogram } from './CalibrationHistogram'

const fail = (title: string) => (err: unknown) =>
  toast.error(title, { description: err instanceof ApiError ? err.message : String(err) })

export function RuleTestsPanel({ rule }: { rule: RuleDetail }) {
  const cases = useRuleTestCases(rule.id)
  const runs = useTestRuns(rule.id)
  const [runId, setRunId] = useState<string | null>(null)
  const latestId = runId ?? runs.data?.[0]?.id ?? null
  const run = useTestRun(latestId)
  const runTests = useRunTests()
  const generate = useGenerateTests(rule.id)
  const del = useDeleteTestCase()
  const [status, setStatus] = useState<'draft' | 'live'>('draft')
  const [open, setOpen] = useState<string | null>(null)

  const runAll = async () => {
    try {
      const r = await runTests.mutateAsync({ scope: 'rule', rule_id: rule.id, rule_status: status })
      setRunId(r.id)
      toast.success(`${r.pass_count}/${r.results?.length ?? 0} passing`)
    } catch (err) {
      fail('Test run failed')(err)
    }
  }

  const results = new Map((run.data?.results ?? []).map((r) => [r.test_case_id, r]))
  const summary = run.data
  const total = summary ? summary.pass_count + summary.fail_count + summary.error_count : 0

  return (
    <div className="space-y-4" data-testid="rule-tests">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground" data-testid="tests-summary">
          {cases.data ? `${cases.data.length} test case${cases.data.length === 1 ? '' : 's'}` : 'Loading…'}
          {summary &&
            ` · ${summary.pass_count}/${total} passing · ${summary.rule_status} · ${summary.jev_model ?? 'no Jev calls'} · ` +
              `$${summary.cost_estimate.toFixed(6)} · ${new Date(`${summary.started_at}Z`).toLocaleTimeString()}`}
        </p>
        <div className="flex flex-wrap gap-2">
          <NativeSelect aria-label="Run against" value={status} onChange={(e) => setStatus(e.target.value as 'draft' | 'live')}>
            <option value="draft">draft (v{rule.current_version})</option>
            {rule.live_version && <option value="live">live (v{rule.live_version})</option>}
          </NativeSelect>
          <Button size="sm" onClick={runAll} disabled={runTests.isPending || !cases.data?.length}>
            <PlayIcon /> {runTests.isPending ? 'Running…' : 'Run all'}
          </Button>
          <Button
            size="sm"
            variant="outline"
            disabled={generate.isPending}
            onClick={() =>
              generate.mutateAsync().then((r) => toast.success(`Generated ${r.created.length} case(s)`, { description: `$${r.cost_usd.toFixed(4)}` }), fail('Generation failed'))
            }
          >
            <SparklesIcon /> {generate.isPending ? 'Generating…' : 'Generate cases'}
          </Button>
          <Button asChild variant="ghost" size="sm">
            <Link to={`/playground?rule=${encodeURIComponent(rule.id)}`}>Try in playground</Link>
          </Button>
        </div>
      </div>

      {(cases.data?.length ?? 0) > 0 && (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Case</TableHead>
              <TableHead>Expected</TableHead>
              <TableHead>Actual</TableHead>
              <TableHead>Value</TableHead>
              <TableHead>Result</TableHead>
              <TableHead>Origin</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {cases.data?.map((tc) => {
              const r = results.get(tc.id)
              const answers = r ? Object.values(r.jev?.[rule.id] ?? {}) : []
              return (
                <Fragment key={tc.id}>
                  <TableRow data-testid={`case-${tc.name}`}>
                    <TableCell>{tc.name}</TableCell>
                    <TableCell>
                      <VerdictBadge verdict={tc.expected_verdict} />
                    </TableCell>
                    <TableCell>{r?.actual ? <VerdictBadge verdict={r.actual} /> : '—'}</TableCell>
                    <TableCell className="font-mono text-xs">{answers.map((a) => a.value.toFixed(2)).join(', ') || '—'}</TableCell>
                    <TableCell>
                      {!r ? (
                        <span className="text-xs text-muted-foreground">not run</span>
                      ) : r.passed ? (
                        <span className="text-xs text-emerald-700">✓ pass</span>
                      ) : (
                        <button type="button" className="text-xs text-destructive underline" onClick={() => setOpen(open === tc.id ? null : tc.id)}>
                          ✗ {r.error ? 'error' : 'fail'} (why)
                        </button>
                      )}
                    </TableCell>
                    <TableCell className="text-xs">{tc.origin}</TableCell>
                    <TableCell>
                      <Button size="icon-sm" variant="ghost" aria-label={`Delete ${tc.name}`} onClick={() => del.mutateAsync(tc.id).catch(fail('Delete failed'))}>
                        <Trash2Icon />
                      </Button>
                    </TableCell>
                  </TableRow>
                  {open === tc.id && r && (
                    <TableRow>
                      <TableCell colSpan={7} className="bg-muted/40 text-xs">
                        {r.error && <div className="text-destructive">Error: {r.error}</div>}
                        <div>{r.reason}</div>
                        {answers.map((a, i) => (
                          <div key={i} className="font-mono">
                            value {a.value.toFixed(2)} → {a.band}
                          </div>
                        ))}
                      </TableCell>
                    </TableRow>
                  )}
                </Fragment>
              )
            })}
          </TableBody>
        </Table>
      )}

      {rule.has_jev && latestId && <CalibrationPanel rule={rule} runId={latestId} />}
    </div>
  )
}

function CalibrationPanel({ rule, runId }: { rule: RuleDetail; runId: string }) {
  const calibrate = useCalibrate(rule.id)
  const apply = useApplyBands(rule.id)
  const [result, setResult] = useState<CalibrationResult | null>(null)

  const suggest = () => calibrate.mutateAsync(runId).then((r) => setResult(r as CalibrationResult), fail('Calibration failed'))
  const changed = result?.questions.filter(
    (q) => q.suggested.bands.escalate_at !== q.current.bands.escalate_at || q.suggested.bands.deny_at !== q.current.bands.deny_at,
  )
  const applyAll = async () => {
    if (!changed?.length) return
    try {
      const r = await apply.mutateAsync(Object.fromEntries(changed.map((q) => [q.question_id, q.suggested.bands])))
      toast.success(`Applied to draft v${r.current_version}; run the tests again`)
      setResult(null)
    } catch (err) {
      fail('Apply failed')(err)
    }
  }

  return (
    <section aria-label="Calibration" className="space-y-3 rounded-lg border p-4" data-testid="calibration">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold">Calibration</h3>
          <p className="text-xs text-muted-foreground">Fits thresholds on the stored answers of the latest run — no new Jev calls.</p>
        </div>
        <Button size="sm" variant="outline" onClick={suggest} disabled={calibrate.isPending}>
          Suggest thresholds
        </Button>
      </div>
      {result?.notes?.map((n) => (
        <p key={n} className="text-xs text-muted-foreground">
          {n}
        </p>
      ))}
      {result?.questions.map((q) => (
        <div key={q.question_id} className="space-y-2">
          <div className="text-xs">
            <span className="font-mono">{q.question_id}</span> · current {q.current.bands.escalate_at}/{q.current.bands.deny_at} → {q.current.correct}/
            {q.current.total} · suggested{' '}
            <strong data-testid={`suggested-${q.question_id}`}>
              {q.suggested.bands.escalate_at}/{q.suggested.bands.deny_at}
            </strong>{' '}
            → {q.suggested.correct}/{q.suggested.total}
          </div>
          <CalibrationHistogram points={q.points} range={q.range as [number, number]} current={q.current.bands} suggested={q.suggested.bands} />
        </div>
      ))}
      {result && (
        <Button size="sm" onClick={applyAll} disabled={!changed?.length || apply.isPending}>
          {changed?.length ? 'Apply to draft' : 'Current thresholds are already best'}
        </Button>
      )}
    </section>
  )
}
