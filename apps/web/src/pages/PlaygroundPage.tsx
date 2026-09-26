import { PlayIcon } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useLocation, useSearchParams } from 'react-router'
import { toast } from 'sonner'
import { useEvaluate, useExamples, useLoadPack, usePlaygroundRuns } from '@/api/playground'
import { ApiError } from '@/api/problem'
import { useRules } from '@/api/rules'
import type { CheckRequest, EvaluateResponse, EvaluateScope, RuleSpec } from '@/api/types'
import { DecisionPanel } from '@/components/decision/DecisionPanel'
import { SaveTestCase } from '@/components/playground/SaveTestCase'
import { ScenarioBuilder } from '@/components/playground/ScenarioBuilder'
import { VerdictBadge } from '@/components/rules/badges'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { NativeSelect } from '@/components/ui-extra/native-select'
import { type CheckRequestForm, emptyForm, formFromRequest, requestFromForm } from '@/lib/checkRequestForm'

type ScopeKind = EvaluateScope['kind']

export function PlaygroundPage() {
  const [params] = useSearchParams()
  const preselected = params.get('rule')
  // "Try in playground" from a fresh translation passes unsaved rules (+ a generated test).
  const handoff = useLocation().state as { inlineRules?: RuleSpec[]; checkRequest?: CheckRequest } | null
  const inlineRules = handoff?.inlineRules ?? []
  const [form, setForm] = useState<CheckRequestForm>(() =>
    handoff?.checkRequest ? formFromRequest(handoff.checkRequest) : emptyForm(),
  )
  const [scopeKind, setScopeKind] = useState<ScopeKind>(inlineRules.length ? 'inline' : preselected ? 'rules' : 'draft')
  const [selected, setSelected] = useState<string[]>(preselected ? [preselected] : [])
  const [result, setResult] = useState<{ response: EvaluateResponse; request: CheckRequest } | null>(null)
  const [formErrors, setFormErrors] = useState<string[]>([])

  const examples = useExamples()
  const runs = usePlaygroundRuns()
  const rules = useRules({})
  const evaluate = useEvaluate()
  const loadPack = useLoadPack()

  // Example chosen via ?example=<id> (e.g. from "Try in playground").
  const exampleParam = params.get('example')
  useEffect(() => {
    const ex = examples.data?.find((e) => e.id === exampleParam)
    if (ex) setForm(formFromRequest(ex.check_request))
  }, [exampleParam, examples.data])

  const scope: EvaluateScope = useMemo(
    () => ({
      kind: scopeKind,
      rule_ids: scopeKind === 'rules' ? selected : [],
      inline_rules: scopeKind === 'inline' ? inlineRules : [],
    }),
    [scopeKind, selected, inlineRules],
  )

  const run = async () => {
    const { request, errors } = requestFromForm(form)
    setFormErrors(errors)
    if (!request) return
    try {
      const response = await evaluate.mutateAsync({ check_request: request, scope })
      setResult({ response, request })
    } catch (err) {
      const detail = err instanceof ApiError ? err.fieldErrors.map((f) => `${f.field}: ${f.message}`).join('\n') || err.message : String(err)
      toast.error('Evaluation failed', { description: detail })
    }
  }

  const loadExample = (id: string) => {
    const ex = examples.data?.find((e) => e.id === id)
    if (ex) {
      setForm(formFromRequest(ex.check_request))
      setResult(null)
    }
  }

  const loadDemoRules = async () => {
    const res = await loadPack.mutateAsync('demo')
    toast.success(`Demo rules: ${res.created.length} created, ${res.skipped.length} already present`)
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold">Playground</h1>
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <NativeSelect aria-label="Load example" value="" onChange={(e) => loadExample(e.target.value)}>
            <option value="">Load example…</option>
            {examples.data?.map((ex) => (
              <option key={ex.id} value={ex.id}>
                {ex.title}
              </option>
            ))}
          </NativeSelect>
          <Button variant="outline" size="sm" onClick={loadDemoRules} disabled={loadPack.isPending}>
            Load demo rules
          </Button>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <section aria-label="Scenario" className="min-w-0 space-y-3">
          <ScenarioBuilder value={form} onChange={setForm} />
          <div className="space-y-2 rounded-md border p-2">
            <div className="flex flex-wrap items-center gap-2 text-sm">
              Evaluate against
              <NativeSelect aria-label="Scope" value={scopeKind} onChange={(e) => setScopeKind(e.target.value as ScopeKind)}>
                <option value="draft">Draft rules (latest versions)</option>
                <option value="live">Live rules (published)</option>
                <option value="rules">Selected rules…</option>
                {inlineRules.length > 0 && (
                  <option value="inline">Unsaved: {inlineRules.map((r) => r.id).join(', ')}</option>
                )}
              </NativeSelect>
            </div>
            {scopeKind === 'rules' && (
              <div className="flex max-h-40 flex-col gap-1 overflow-auto" data-testid="scope-rules">
                {rules.data?.map((r) => (
                  <label key={r.id} className="flex items-center gap-2 text-xs">
                    <Checkbox
                      aria-label={`Include ${r.id}`}
                      checked={selected.includes(r.id)}
                      onCheckedChange={(on) => setSelected(on ? [...selected, r.id] : selected.filter((x) => x !== r.id))}
                    />
                    <span className="font-mono">{r.id}</span> <span className="text-muted-foreground">{r.status}</span>
                  </label>
                ))}
              </div>
            )}
          </div>
          {formErrors.length > 0 && (
            <ul className="text-xs text-destructive" role="alert">
              {formErrors.map((e) => (
                <li key={e}>{e}</li>
              ))}
            </ul>
          )}
          <Button onClick={run} disabled={evaluate.isPending || (scopeKind === 'rules' && selected.length === 0)}>
            <PlayIcon /> {evaluate.isPending ? 'Running…' : 'Run'}
          </Button>
        </section>

        <section aria-label="Decision" className="min-w-0 space-y-3">
          {result ? (
            <>
              <DecisionPanel decision={result.response.decision} rules={result.response.rules} />
              <SaveTestCase
                key={result.response.run_id}
                checkRequest={result.request}
                decision={result.response.decision}
                rules={result.response.rules}
              />
            </>
          ) : (
            <p className="rounded-lg border border-dashed p-6 text-sm text-muted-foreground">
              Build a check request (or load an example) and press Run to see the decision.
            </p>
          )}
          <div>
            <h2 className="mb-1 text-sm font-semibold">Recent runs</h2>
            <ul className="divide-y rounded-md border text-xs" data-testid="run-history">
              {runs.data?.length === 0 && <li className="p-2 text-muted-foreground">No runs yet.</li>}
              {runs.data?.map((r) => (
                <li key={r.id}>
                  <button
                    type="button"
                    className="flex w-full items-center gap-2 p-2 text-left hover:bg-muted/50"
                    onClick={() => setForm(formFromRequest(r.check_request))}
                  >
                    <VerdictBadge verdict={r.decision.verdict} />
                    <span className="font-mono">{r.check_request.request.tool ?? r.check_request.request.kind}</span>
                    <span className="text-muted-foreground">{r.scope.kind}</span>
                    <span className="ml-auto text-muted-foreground">{new Date(`${r.created_at}Z`).toLocaleTimeString()}</span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        </section>
      </div>
    </div>
  )
}
