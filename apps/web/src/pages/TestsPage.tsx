import { PlayIcon } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { ApiError } from '@/api/problem'
import { useRunTests, useTestRun, useTestRuns } from '@/api/tests'
import { VerdictBadge } from '@/components/rules/badges'
import { Button } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { NativeSelect } from '@/components/ui-extra/native-select'

export function TestsPage() {
  const [status, setStatus] = useState<'draft' | 'live'>('draft')
  const [runId, setRunId] = useState<string | null>(null)
  const runs = useTestRuns(null)
  const run = useTestRun(runId)
  const runTests = useRunTests()

  const runAll = async () => {
    try {
      const r = await runTests.mutateAsync({ scope: 'policy', rule_status: status })
      setRunId(r.id)
    } catch (err) {
      toast.error('Test run failed', { description: err instanceof ApiError ? err.message : String(err) })
    }
  }

  const byRule = new Map<string, NonNullable<typeof run.data>['results']>()
  for (const r of run.data?.results ?? []) {
    const key = r.rule_id ?? '(policy-wide)'
    byRule.set(key, [...(byRule.get(key) ?? []), r])
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold">Tests</h1>
        <div className="flex gap-2">
          <NativeSelect aria-label="Run against" value={status} onChange={(e) => setStatus(e.target.value as 'draft' | 'live')}>
            <option value="draft">draft rules</option>
            <option value="live">live rules</option>
          </NativeSelect>
          <Button onClick={runAll} disabled={runTests.isPending}>
            <PlayIcon /> {runTests.isPending ? 'Running…' : 'Run every test case'}
          </Button>
        </div>
      </div>
      {run.data && (
        <p className="text-sm" data-testid="policy-summary">
          {run.data.pass_count} passed · {run.data.fail_count} failed · {run.data.error_count} errors · {run.data.jev_model ?? 'no Jev calls'} · $
          {run.data.cost_estimate.toFixed(6)}
        </p>
      )}
      {[...byRule.entries()].map(([ruleId, results]) => (
        <section key={ruleId} className="space-y-1">
          <h2 className="text-sm font-semibold">
            {ruleId === '(policy-wide)' ? ruleId : <Link to={`/rules/${ruleId}`} className="hover:underline">{ruleId}</Link>}{' '}
            <span className="text-xs font-normal text-muted-foreground">
              {results?.filter((r) => r.passed).length}/{results?.length}
            </span>
          </h2>
          <Table>
            <TableBody>
              {results?.map((r) => (
                <TableRow key={r.test_case_id}>
                  <TableCell className="w-1/3">{r.name}</TableCell>
                  <TableCell>
                    expect <VerdictBadge verdict={r.expected} />
                  </TableCell>
                  <TableCell>{r.actual ? <VerdictBadge verdict={r.actual} /> : '—'}</TableCell>
                  <TableCell className="text-xs">{r.passed ? '✓' : r.error ? `error: ${r.error}` : '✗'}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </section>
      ))}
      <section>
        <h2 className="mb-1 text-sm font-semibold">Recent runs</h2>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>When</TableHead>
              <TableHead>Scope</TableHead>
              <TableHead>Result</TableHead>
              <TableHead>Jev</TableHead>
              <TableHead>Cost</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {runs.data?.map((r) => (
              <TableRow key={r.id} className="cursor-pointer" onClick={() => setRunId(r.id)}>
                <TableCell className="text-xs">{new Date(`${r.started_at}Z`).toLocaleString()}</TableCell>
                <TableCell className="text-xs">
                  {r.scope === 'rule' ? r.rule_id : 'all cases'} · {r.rule_status}
                </TableCell>
                <TableCell className="text-xs">
                  {r.pass_count}/{r.pass_count + r.fail_count + r.error_count}
                </TableCell>
                <TableCell className="font-mono text-xs">{r.jev_model ?? '—'}</TableCell>
                <TableCell className="text-xs">${r.cost_estimate.toFixed(6)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </section>
    </div>
  )
}
