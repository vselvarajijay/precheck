import { useState } from 'react'
import { toast } from 'sonner'
import { fetchLabRun, useLabRuns, useScenarios, useStartRun } from '@/features/lab/api'
import { ApiError } from '@/shared/api/problem'
import type { LabRun } from '@/shared/api/types'
import { Badge } from '@/shared/ui/badge'
import { Button } from '@/shared/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/shared/ui/table'
import { RUN_STATUS_STYLE } from '@/features/lab/lib'

const POLL_MS = 500
const RUN_TIMEOUT_MS = 120_000

async function waitForRun(id: string): Promise<LabRun> {
  const deadline = Date.now() + RUN_TIMEOUT_MS
  for (;;) {
    const run = await fetchLabRun(id).catch(() => null)
    if (run && run.status !== 'running') return run
    if (Date.now() > deadline) throw new Error(`run ${id} did not finish`)
    await new Promise((r) => setTimeout(r, POLL_MS))
  }
}

export function ScenarioSuite({ onOpenRun }: { onOpenRun: (id: string) => void }) {
  const scenarios = useScenarios()
  const runs = useLabRuns()
  const start = useStartRun()
  const [busy, setBusy] = useState<string | null>(null)
  const [open, setOpen] = useState<string | null>(null)

  const history = (scenarioId: string) => (runs.data ?? []).filter((r) => r.scenario_id === scenarioId)

  const runOne = async (scenarioId: string) => {
    const { id } = await start.mutateAsync({ mode: 'scripted', scenario_id: scenarioId })
    return waitForRun(id)
  }

  const runAll = async () => {
    setBusy('*')
    let passed = 0
    const list = scenarios.data ?? []
    try {
      for (const s of list) {
        setBusy(s.id)
        if ((await runOne(s.id)).status === 'passed') passed++
      }
      toast[passed === list.length ? 'success' : 'error'](`${passed}/${list.length} scenarios passed`)
    } catch (err) {
      toast.error('Run all stopped', { description: err instanceof ApiError ? err.message : String(err) })
    } finally {
      setBusy(null)
      runs.refetch()
    }
  }

  const runSingle = async (scenarioId: string) => {
    setBusy(scenarioId)
    try {
      const run = await runOne(scenarioId)
      onOpenRun(run.id)
    } catch (err) {
      toast.error('Run failed to start', { description: err instanceof ApiError ? err.message : String(err) })
    } finally {
      setBusy(null)
      runs.refetch()
    }
  }

  return (
    <section className="space-y-3" aria-label="Scenario suite">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">Scripted scenarios against the live policy, through the enforcement proxy.</p>
        <Button size="sm" onClick={runAll} disabled={!!busy || !scenarios.data?.length}>
          {busy ? 'Running…' : 'Run all'}
        </Button>
      </div>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Scenario</TableHead>
            <TableHead>Steps</TableHead>
            <TableHead>Last result</TableHead>
            <TableHead className="text-right">Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {(scenarios.data ?? []).map((s) => {
            const h = history(s.id)
            const last = h[0]
            return [
              <TableRow key={s.id} data-testid={`scenario-${s.id}`}>
                <TableCell>
                  <div className="font-medium">{s.title}</div>
                  <div className="font-mono text-[11px] text-muted-foreground">{s.id}</div>
                </TableCell>
                <TableCell>{s.steps.length}</TableCell>
                <TableCell>
                  {busy === s.id ? (
                    <Badge variant="outline" className={RUN_STATUS_STYLE.running}>running</Badge>
                  ) : last ? (
                    <button type="button" className="cursor-pointer" onClick={() => onOpenRun(last.id)} aria-label={`Open last run of ${s.id}`}>
                      <Badge variant="outline" className={RUN_STATUS_STYLE[last.status]} data-testid="last-status">
                        {last.status}
                      </Badge>
                    </button>
                  ) : (
                    <span className="text-xs text-muted-foreground">never run</span>
                  )}
                </TableCell>
                <TableCell className="space-x-2 text-right">
                  <Button size="sm" variant="outline" onClick={() => setOpen(open === s.id ? null : s.id)} disabled={h.length === 0}>
                    History ({h.length})
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => runSingle(s.id)} disabled={!!busy}>
                    Run
                  </Button>
                </TableCell>
              </TableRow>,
              open === s.id && (
                <TableRow key={`${s.id}-history`}>
                  <TableCell colSpan={4}>
                    <ul className="space-y-1 text-xs">
                      {h.map((r) => (
                        <li key={r.id} className="flex items-center gap-2">
                          <Badge variant="outline" className={RUN_STATUS_STYLE[r.status]}>{r.status}</Badge>
                          <button type="button" className="font-mono underline" onClick={() => onOpenRun(r.id)}>
                            {r.id.slice(0, 8)}
                          </button>
                          <span className="text-muted-foreground">
                            {r.started_at ? new Date(r.started_at + 'Z').toLocaleString() : ''}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </TableCell>
                </TableRow>
              ),
            ]
          })}
        </TableBody>
      </Table>
    </section>
  )
}
