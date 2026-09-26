import { LanguagesIcon } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router'
import { toast } from 'sonner'
import { ApiError } from '@/api/problem'
import { type TranslateStage, translateStream, useAnswerClarifications, useRefineRule, useSaveTranslation } from '@/api/translate'
import { GATES, type Gate, type RuleSpec, type TranslateResponse, type TranslationWarning } from '@/api/types'
import { ClarificationsPanel } from '@/components/translate/ClarificationsPanel'
import { ProgressSteps } from '@/components/translate/ProgressSteps'
import { TranslatedRuleCard } from '@/components/translate/TranslatedRuleCard'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { NativeSelect } from '@/components/ui-extra/native-select'

type Result = TranslateResponse['result']
type NormalizedResult = Result & {
  rules: NonNullable<Result['rules']>
  tests: NonNullable<Result['tests']>
  errors: string[]
  requirements: NonNullable<Result['requirements']>
  clarifications: NonNullable<Result['clarifications']>
  warnings: NonNullable<Result['warnings']>
}

/** Fill server defaults so the UI never deals with missing lists. */
function normalize(r: Result): NormalizedResult {
  return {
    ...r,
    rules: r.rules ?? [],
    tests: r.tests ?? [],
    errors: r.errors ?? [],
    requirements: r.requirements ?? [],
    clarifications: r.clarifications ?? [],
    warnings: r.warnings ?? [],
  }
}

const splitList = (s: string) =>
  s
    .split(',')
    .map((x) => x.trim())
    .filter(Boolean)

export function TranslatePage() {
  const navigate = useNavigate()
  const [text, setText] = useState('')
  const [gate, setGate] = useState<Gate | ''>('')
  const [tools, setTools] = useState('')
  const [purpose, setPurpose] = useState('')
  const [domains, setDomains] = useState('')

  const [running, setRunning] = useState(false)
  const [stage, setStage] = useState<TranslateStage | null>(null)
  const [repairs, setRepairs] = useState(0)
  const [response, setResponse] = useState<TranslateResponse | null>(null)
  const [specs, setSpecs] = useState<RuleSpec[]>([])
  const [warnings, setWarnings] = useState<Record<string, TranslationWarning[]>>({})
  const [refiningId, setRefiningId] = useState<string | null>(null)

  const caseId = response?.business_case_id ?? null
  const answer = useAnswerClarifications(caseId)
  const save = useSaveTranslation(caseId)
  const refine = useRefineRule()
  const result = response ? normalize(response.result) : null

  const accept = (r: TranslateResponse) => {
    const rules = r.result.rules ?? []
    setResponse(r)
    setSpecs(rules.map((t) => t.spec))
    setWarnings(Object.fromEntries(rules.map((t) => [t.spec.id, t.warnings ?? []])))
  }

  const translate = async () => {
    setRunning(true)
    setResponse(null)
    setRepairs(0)
    setStage('plan')
    try {
      const r = await translateStream(
        {
          text,
          gate_hint: gate || null,
          tools: splitList(tools),
          agent_purpose: purpose || null,
          domains: splitList(domains),
          answers: {},
        },
        (s) => {
          setStage(s)
          if (s === 'repairing') setRepairs((n) => n + 1)
        },
      )
      accept(r)
    } catch (err) {
      toast.error('Translation failed', { description: err instanceof ApiError ? err.message : String(err) })
    } finally {
      setRunning(false)
      setStage(null)
    }
  }

  const submitAnswers = async (answers: Record<string, string>) => {
    try {
      accept(await answer.mutateAsync(answers))
    } catch (err) {
      toast.error('Re-translation failed', { description: err instanceof ApiError ? err.message : String(err) })
    }
  }

  const testsFor = (id: string) => result?.tests.filter((t) => t.rule_id === id) ?? []

  const saveAll = async () => {
    const kept = new Set(specs.map((s) => s.id))
    try {
      const res = await save.mutateAsync({
        rules: specs,
        tests: (result?.tests ?? []).filter((t) => kept.has(t.rule_id)).map((t) => ({ rule_id: t.rule_id, test: t.test })),
      })
      toast.success(`Saved ${res.rules.length} draft rule(s) and ${res.tests_created} test case(s)`)
      navigate('/rules')
    } catch (err) {
      toast.error('Save failed', { description: err instanceof ApiError ? err.message : String(err) })
    }
  }

  const refineRule = async (spec: RuleSpec, instruction: string) => {
    setRefiningId(spec.id)
    try {
      const r = await refine.mutateAsync({ rule: spec, instruction })
      if (r.rule) {
        const refined = r.rule.spec
        setSpecs((all) => all.map((s) => (s.id === spec.id ? refined : s)))
        setWarnings((w) => ({ ...w, [refined.id]: r.rule?.warnings ?? [] }))
        toast.success(`Refined ${refined.id}`, { description: `$${r.cost_usd.toFixed(4)}` })
      } else toast.error('Refine failed', { description: (r.errors ?? []).join('\n') })
    } catch (err) {
      toast.error('Refine failed', { description: err instanceof ApiError ? err.message : String(err) })
    } finally {
      setRefiningId(null)
    }
  }

  const tryRule = (spec: RuleSpec) => {
    const example = testsFor(spec.id)[0]
    navigate('/playground', { state: { inlineRules: [spec], checkRequest: example?.test.check_request } })
  }

  return (
    <div className="max-w-5xl space-y-5">
      <h1 className="text-xl font-semibold">New rules from a business case</h1>
      <section aria-label="Describe the business case" className="space-y-3 rounded-lg border p-4">
        <label className="block text-sm">
          Describe the rule in plain language
          <Textarea
            aria-label="Business case"
            rows={4}
            placeholder="Refunds over $500 need a manager. Never refund to a different card than the one used for the purchase."
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
        </label>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="text-sm">
            Gate hint
            <NativeSelect aria-label="Gate hint" className="block w-full" value={gate} onChange={(e) => setGate(e.target.value as Gate | '')}>
              <option value="">Let the translator decide</option>
              {GATES.map((g) => (
                <option key={g} value={g}>
                  {g}
                </option>
              ))}
            </NativeSelect>
          </label>
          <label className="text-sm">
            Tools (comma separated)
            <Input aria-label="Tools" placeholder="issue_refund, lookup_order" value={tools} onChange={(e) => setTools(e.target.value)} />
          </label>
          <label className="text-sm">
            Agent purpose
            <Input aria-label="Agent purpose" placeholder="Handles customer support…" value={purpose} onChange={(e) => setPurpose(e.target.value)} />
          </label>
          <label className="text-sm">
            Our domains (comma separated)
            <Input aria-label="Domains" placeholder="example-shop.com" value={domains} onChange={(e) => setDomains(e.target.value)} />
          </label>
        </div>
        <div className="flex flex-wrap items-center gap-4">
          <Button onClick={translate} disabled={!text.trim() || running}>
            <LanguagesIcon /> {running ? 'Translating…' : 'Translate'}
          </Button>
          {(running || result) && <ProgressSteps stage={stage} repairs={repairs || (result?.repair_rounds ?? 0)} done={!running && !!result} />}
        </div>
      </section>

      {result && (
        <>
          <div className="text-xs text-muted-foreground" data-testid="translation-meta">
            {result.status} · {result.provenance.translator_model} · {result.provenance.prompt_version} · $
            {result.cost_usd.toFixed(4)}
          </div>
          {result.errors.length > 0 && (
            <ul className="rounded-md border border-destructive/40 p-3 text-xs text-destructive" role="alert">
              {result.errors.map((e) => (
                <li key={e}>{e}</li>
              ))}
            </ul>
          )}
          {result.requirements.length > 0 && (
            <section aria-label="Requirements" className="space-y-1">
              <h2 className="text-sm font-semibold">Requirements found</h2>
              <ul className="space-y-1 text-sm">
                {result.requirements.map((r) => (
                  <li key={r.requirement} className="flex gap-2">
                    <span className="w-24 shrink-0 rounded bg-muted px-1.5 text-center text-xs leading-5">{r.routing}</span>
                    <span>
                      {r.requirement} <span className="text-xs text-muted-foreground">— {r.routing_reason}</span>
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          )}
          {result.clarifications.length > 0 && (
            <ClarificationsPanel
              key={caseId + result.status}
              clarifications={result.clarifications}
              blocking={result.status === 'needs_clarification'}
              busy={answer.isPending}
              onSubmit={submitAnswers}
            />
          )}
          {result.warnings.length > 0 && (
            <ul className="rounded-md border border-amber-200 bg-amber-50 p-2 text-xs text-amber-900">
              {result.warnings.map((w, i) => (
                <li key={i}>
                  <span className="font-mono">{w.code}</span>: {w.message}
                </li>
              ))}
            </ul>
          )}
          {specs.length > 0 && (
            <section aria-label="Generated rules" className="space-y-3">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold">Generated rules ({specs.length})</h2>
                <Button onClick={saveAll} disabled={save.isPending}>
                  {save.isPending ? 'Saving…' : 'Save all as draft'}
                </Button>
              </div>
              {specs.map((spec) => (
                <TranslatedRuleCard
                  key={spec.id}
                  spec={spec}
                  warnings={warnings[spec.id] ?? []}
                  tests={testsFor(spec.id)}
                  onChange={(next) => setSpecs((all) => all.map((s) => (s.id === spec.id ? next : s)))}
                  onRemove={() => setSpecs((all) => all.filter((s) => s.id !== spec.id))}
                  onTry={() => tryRule(spec)}
                  onRefine={(instruction) => refineRule(spec, instruction)}
                  refining={refiningId === spec.id}
                />
              ))}
            </section>
          )}
        </>
      )}
    </div>
  )
}
