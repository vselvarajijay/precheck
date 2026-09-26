import { useMemo, useState } from 'react'
import { toast } from 'sonner'
import { useEscalations, useLabRun, useLivePolicy, useRetryStep, useRunEvents, useScenarios, useStartRun } from '@/features/lab/api'
import { ApiError } from '@/shared/api/problem'
import type { RuleInfo, RunStep } from '@/shared/api/types'
import { EscalationQueue } from '@/features/lab/components/EscalationQueue'
import { RunTimeline } from '@/features/lab/components/RunTimeline'
import { mergeSteps } from '@/features/lab/lib'
import { ScenarioSuite } from '@/features/lab/components/ScenarioSuite'
import { Button } from '@/shared/ui/button'
import { Label } from '@/shared/ui/label'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/shared/ui/tabs'
import { Textarea } from '@/shared/ui/textarea'
import { NativeSelect } from '@/shared/ui/native-select'

const AGENTS = ['support-bot', 'research-bot']

export function AgentLabPage() {
  const [tab, setTab] = useState('run')
  const [runId, setRunId] = useState<string | null>(null)
  const policy = useLivePolicy()
  const pending = useEscalations('pending')
  const rules = useMemo<Record<string, RuleInfo>>(
    () =>
      Object.fromEntries(
        (policy.data?.rules ?? []).map((r) => [r.id, { id: r.id, name: r.name, status: 'live', version: r.version, body: r.body }]),
      ),
    [policy.data],
  )

  const openRun = (id: string) => {
    setRunId(id)
    setTab('run')
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold">Agent Lab</h1>
        <p className="text-sm text-muted-foreground">
          Run the test agent through the enforcement proxy against the live policy
          {policy.data?.policy_version ? ` (policy v${policy.data.policy_version})` : ''}.
        </p>
      </div>
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="run">Run</TabsTrigger>
          <TabsTrigger value="scenarios">Scenarios</TabsTrigger>
          <TabsTrigger value="escalations">
            Escalations{pending.data?.length ? ` (${pending.data.length})` : ''}
          </TabsTrigger>
        </TabsList>
        <TabsContent value="run" className="pt-3">
          <RunPanel runId={runId} onStarted={setRunId} rules={rules} />
        </TabsContent>
        <TabsContent value="scenarios" className="pt-3">
          <ScenarioSuite onOpenRun={openRun} />
        </TabsContent>
        <TabsContent value="escalations" className="pt-3">
          <EscalationQueue rules={rules} />
        </TabsContent>
      </Tabs>
    </div>
  )
}

function RunPanel({ runId, onStarted, rules }: { runId: string | null; onStarted: (id: string) => void; rules: Record<string, RuleInfo> }) {
  const scenarios = useScenarios()
  const start = useStartRun()
  const [mode, setMode] = useState<'scripted' | 'llm'>('scripted')
  const [scenarioId, setScenarioId] = useState('')
  const [goal, setGoal] = useState('')
  const [agentId, setAgentId] = useState(AGENTS[0])
  const stream = useRunEvents(runId)
  const detail = useLabRun(stream.done ? runId : null)
  const [retried, setRetried] = useState<RunStep[]>([])
  const retry = useRetryStep(runId ?? '')

  const chosen = scenarioId || scenarios.data?.[0]?.id || ''
  const run = stream.done ?? detail.data ?? (runId ? { id: runId, mode, status: 'running' as const } : null)
  const steps = mergeSteps(stream.steps, stream.done?.steps, detail.data?.steps, retried)

  const submit = async () => {
    try {
      const started = await start.mutateAsync(
        mode === 'scripted' ? { mode, scenario_id: chosen } : { mode, goal, agent_id: agentId },
      )
      setRetried([])
      onStarted(started.id)
    } catch (err) {
      toast.error('Could not start run', { description: err instanceof ApiError ? err.message : String(err) })
    }
  }

  const onRetry = async (index: number) => {
    try {
      const step = await retry.mutateAsync(index)
      setRetried((r) => [...r, step])
      toast.message(`Retried step ${index}: ${step.verdict}`)
    } catch (err) {
      toast.error('Retry failed', { description: err instanceof ApiError ? err.message : String(err) })
    }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[320px_1fr]">
      <div className="space-y-3 rounded-lg border p-3" aria-label="Run panel" role="group">
        <div className="space-y-1">
          <Label htmlFor="lab-mode">Mode</Label>
          <NativeSelect id="lab-mode" value={mode} onChange={(e) => setMode(e.target.value as 'scripted' | 'llm')}>
            <option value="scripted">Scripted scenario</option>
            <option value="llm">LLM goal (Claude)</option>
          </NativeSelect>
        </div>
        {mode === 'scripted' ? (
          <div className="space-y-1">
            <Label htmlFor="lab-scenario">Scenario</Label>
            <NativeSelect id="lab-scenario" value={chosen} onChange={(e) => setScenarioId(e.target.value)}>
              {(scenarios.data ?? []).map((s) => (
                <option key={s.id} value={s.id}>
                  {s.title}
                </option>
              ))}
            </NativeSelect>
            <p className="text-xs text-muted-foreground">{scenarios.data?.find((s) => s.id === chosen)?.description}</p>
          </div>
        ) : (
          <>
            <div className="space-y-1">
              <Label htmlFor="lab-agent">Agent profile</Label>
              <NativeSelect id="lab-agent" value={agentId} onChange={(e) => setAgentId(e.target.value)}>
                {AGENTS.map((a) => (
                  <option key={a} value={a}>
                    {a}
                  </option>
                ))}
              </NativeSelect>
            </div>
            <div className="space-y-1">
              <Label htmlFor="lab-goal">Goal</Label>
              <Textarea id="lab-goal" rows={4} value={goal} onChange={(e) => setGoal(e.target.value)} placeholder="What the user asks the agent" />
            </div>
          </>
        )}
        <Button onClick={submit} disabled={start.isPending || (mode === 'llm' ? !goal.trim() : !chosen)}>
          {start.isPending ? 'Starting…' : 'Run'}
        </Button>
      </div>
      <div>
        {stream.error && <p className="text-sm text-destructive">{stream.error}</p>}
        {run ? (
          <RunTimeline run={run} steps={steps} rules={rules} onRetry={onRetry} retrying={retry.isPending} />
        ) : (
          <p className="text-sm text-muted-foreground">Start a run to see its steps here as they happen.</p>
        )}
      </div>
    </div>
  )
}
