import { PlusIcon, XIcon } from 'lucide-react'
import { type ReactNode, useCallback, useEffect, useMemo, useState } from 'react'
import { validateRuleBody } from '@/features/rules/api'
import type { JevCheck, RuleBody, Verdict } from '@/shared/api/types'
import { SEVERITIES, VERDICTS } from '@/shared/api/types'
import { Button } from '@/shared/ui/button'
import { Checkbox } from '@/shared/ui/checkbox'
import { Input } from '@/shared/ui/input'
import { Switch } from '@/shared/ui/switch'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/shared/ui/tabs'
import { NativeSelect } from '@/shared/ui/native-select'
import { useDebounced } from '@/shared/hooks/useDebounced'
import {
  CHECK_PATHS,
  defaultOutcome,
  defaultPredicate,
  isPinned,
  localProblems,
  newJevCheck,
  newQuestion,
  syncOutcome,
} from '@/shared/lib/ruleBody'
import { FieldErrors, FieldErrorsContext } from './FieldErrors'
import { JevQuestionEditor } from './JevQuestionEditor'
import { JsonBodyEditor } from './JsonBodyEditor'
import { OutcomeEditor } from './OutcomeEditor'
import { PredicateBuilder } from './PredicateBuilder'

export interface ValidationState {
  checking: boolean
  valid: boolean
  liveProblems: string[]
  contentHash?: string
}

interface Props {
  value: RuleBody
  onChange: (b: RuleBody) => void
  /** Extra errors (e.g. from a failed save), keyed by body path. */
  errors?: Record<string, string[]>
  onValidation?: (v: ValidationState) => void
}

function merge(...maps: Record<string, string[]>[]): Record<string, string[]> {
  const out: Record<string, string[]> = {}
  for (const m of maps) for (const [k, v] of Object.entries(m)) (out[k] ??= []).push(...v)
  return out
}

export function RuleBodyEditor({ value, onChange, errors = {}, onValidation }: Props) {
  const [serverErrors, setServerErrors] = useState<Record<string, string[]>>({})
  const debounced = useDebounced(value, 350)
  const local = useMemo(() => localProblems(value), [value])

  useEffect(() => {
    let cancelled = false
    onValidation?.({ checking: true, valid: false, liveProblems: [] })
    validateRuleBody(debounced)
      .then((r) => {
        if (cancelled) return
        const map: Record<string, string[]> = {}
        for (const f of r.errors) (map[f.field] ??= []).push(f.message)
        setServerErrors(map)
        onValidation?.({
          checking: false,
          valid: r.valid,
          liveProblems: r.live_problems ?? [],
          contentHash: r.content_hash ?? undefined,
        })
      })
      .catch((e: unknown) => {
        if (cancelled) return
        setServerErrors({ '': [`Could not validate: ${(e as Error).message}`] })
        onValidation?.({ checking: false, valid: false, liveProblems: [] })
      })
    return () => {
      cancelled = true
    }
    // onValidation is intentionally not a dependency (callers pass inline callbacks).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debounced])

  const allErrors = useMemo(() => merge(local, serverErrors, errors), [local, serverErrors, errors])
  const set = (patch: Partial<RuleBody>) => onChange({ ...value, ...patch })
  const applyJson = useCallback((b: RuleBody) => onChange(b), [onChange])

  return (
    <FieldErrorsContext.Provider value={allErrors}>
      <Tabs defaultValue="form">
        <TabsList>
          <TabsTrigger value="form">Form</TabsTrigger>
          <TabsTrigger value="json">JSON</TabsTrigger>
        </TabsList>
        <TabsContent value="form" className="space-y-4 pt-2">
          <FieldErrors path="" exact />
          <Section title="When it applies" hint="A cheap selector; rules that don't apply don't participate.">
            <ToggleRow
              label="Only when a condition holds"
              checked={!!value.applies_when}
              onChange={(on) => set({ applies_when: on ? defaultPredicate('eq') : null })}
            >
              {value.applies_when && (
                <PredicateBuilder
                  label="Applies when"
                  value={value.applies_when}
                  errorPath="applies_when"
                  onChange={(p) => set({ applies_when: p })}
                />
              )}
            </ToggleRow>
            {!value.applies_when && <p className="text-xs text-muted-foreground">Applies to every request at this gate.</p>}
          </Section>

          <Section title="Required fields" hint="If the request lacks one of these, the rule gives its on-missing verdict.">
            <PathChecklist
              name="requires"
              selected={value.requires ?? []}
              onChange={(requires) => set({ requires })}
            />
            <VerdictSelect
              label="When missing"
              value={value.on_missing}
              onChange={(on_missing) => set({ on_missing })}
            />
            <FieldErrors path="requires" />
          </Section>

          <Section title="Deterministic check" hint="Numbers, dates, exact matches and allowlists belong here, not in Jev.">
            <ToggleRow
              label="Use a deterministic check"
              checked={!!value.deterministic}
              onChange={(on) =>
                set({
                  deterministic: on
                    ? { predicate: defaultPredicate('gt', 'request.args.amount'), verdict_when_true: 'escalate' }
                    : null,
                })
              }
            >
              {value.deterministic && (
                <div className="space-y-2">
                  <PredicateBuilder
                    label="Deterministic"
                    value={value.deterministic.predicate}
                    errorPath="deterministic.predicate"
                    onChange={(predicate) => set({ deterministic: { ...value.deterministic!, predicate } })}
                  />
                  <VerdictSelect
                    label="When true"
                    value={value.deterministic.verdict_when_true}
                    onChange={(verdict_when_true) =>
                      set({ deterministic: { ...value.deterministic!, verdict_when_true } })
                    }
                  />
                  <p className="text-xs text-muted-foreground">
                    When true, this verdict applies and the rule's Jev check is skipped.
                  </p>
                </div>
              )}
            </ToggleRow>
          </Section>

          <Section title="Jev check" hint="Judgment calls, answered by Jev with calibrated probabilities.">
            <ToggleRow label="Use a Jev check" checked={!!value.jev} onChange={(on) => set({ jev: on ? newJevCheck() : null })}>
              {value.jev && <JevCheckEditor value={value.jev} onChange={(jev) => set({ jev })} />}
            </ToggleRow>
          </Section>

          <Section title="Risk">
            <div className="flex flex-wrap gap-4">
              <label className="flex items-center gap-2 text-sm">
                Severity
                <NativeSelect
                  aria-label="Severity"
                  value={value.severity}
                  onChange={(e) => set({ severity: e.target.value as RuleBody['severity'] })}
                >
                  {SEVERITIES.map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </NativeSelect>
              </label>
              <label className="flex items-center gap-2 text-sm">
                If Jev fails
                <NativeSelect
                  aria-label="On error"
                  value={value.on_error ?? ''}
                  onChange={(e) => set({ on_error: (e.target.value || null) as Verdict | null })}
                >
                  <option value="">default (escalate; ingress allows)</option>
                  {VERDICTS.map((v) => (
                    <option key={v} value={v}>
                      {v}
                    </option>
                  ))}
                </NativeSelect>
              </label>
            </div>
          </Section>
        </TabsContent>
        <TabsContent value="json" className="pt-2">
          <JsonBodyEditor value={value} onApply={applyJson} />
        </TabsContent>
      </Tabs>
    </FieldErrorsContext.Provider>
  )
}

function JevCheckEditor({ value: jev, onChange }: { value: JevCheck; onChange: (j: JevCheck) => void }) {
  const qids = Object.keys(jev.questions)

  const renameQuestion = (from: string, to: string) => {
    if (to === from || to in jev.questions) return
    const rename = <T,>(obj: Record<string, T>) =>
      Object.fromEntries(Object.entries(obj).map(([k, v]) => [k === from ? to : k, v]))
    onChange({ ...jev, questions: rename(jev.questions), outcomes: rename(jev.outcomes) })
  }

  const addQuestion = () => {
    let n = qids.length + 1
    while (`q${n}` in jev.questions) n++
    const q = newQuestion('noul')
    onChange({ ...jev, questions: { ...jev.questions, [`q${n}`]: q }, outcomes: { ...jev.outcomes, [`q${n}`]: defaultOutcome(q) } })
  }

  const removeQuestion = (qid: string) => {
    const { [qid]: _q, ...questions } = jev.questions
    const { [qid]: _o, ...outcomes } = jev.outcomes
    onChange({ ...jev, questions, outcomes })
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <label htmlFor="jev-model">Jev model</label>
        <Input
          id="jev-model"
          aria-label="Jev model"
          className="h-8 w-40 font-mono text-xs"
          value={jev.model}
          onChange={(e) => onChange({ ...jev, model: e.target.value })}
        />
        <span className="text-xs text-muted-foreground">
          {isPinned(jev.model) ? 'pinned' : 'drafts may use jev-latest; publishing needs a pinned version (jev-X.Y.Z)'}
        </span>
        <FieldErrors path="jev.model" />
      </div>
      <div>
        <div className="text-sm font-medium">Looks at</div>
        <p className="mb-1 text-xs text-muted-foreground">Only these request fields are sent to Jev.</p>
        <PathChecklist
          name="state_template"
          selected={jev.state_template}
          onChange={(state_template) => onChange({ ...jev, state_template })}
        />
        <FieldErrors path="jev.state_template" />
      </div>
      <FieldErrors path="jev.questions" exact />
      {qids.map((qid) => (
        <div key={qid} className="space-y-3 rounded-lg border p-3" data-testid={`question-${qid}`}>
          <div className="flex items-center gap-2">
            <label className="text-xs text-muted-foreground" htmlFor={`qid-${qid}`}>
              Question id
            </label>
            <Input
              id={`qid-${qid}`}
              aria-label={`Question id ${qid}`}
              className="h-8 w-48 font-mono text-xs"
              defaultValue={qid}
              onBlur={(e) => renameQuestion(qid, e.target.value.trim())}
            />
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="ml-auto"
              disabled={qids.length <= 1}
              onClick={() => removeQuestion(qid)}
            >
              <XIcon /> Remove question
            </Button>
          </div>
          <JevQuestionEditor
            qid={qid}
            value={jev.questions[qid]!}
            onChange={(q) =>
              onChange({
                ...jev,
                questions: { ...jev.questions, [qid]: q },
                outcomes: { ...jev.outcomes, [qid]: syncOutcome(q, jev.outcomes[qid]) },
              })
            }
          />
          <OutcomeEditor
            qid={qid}
            question={jev.questions[qid]!}
            value={jev.outcomes[qid] ?? defaultOutcome(jev.questions[qid]!)}
            onChange={(o) => onChange({ ...jev, outcomes: { ...jev.outcomes, [qid]: o } })}
          />
        </div>
      ))}
      <Button type="button" variant="outline" size="sm" onClick={addQuestion}>
        <PlusIcon /> Add question
      </Button>
    </div>
  )
}

function Section({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
  return (
    <section className="space-y-2 rounded-lg border p-4" aria-label={title}>
      <h2 className="text-sm font-semibold">{title}</h2>
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
      {children}
    </section>
  )
}

function ToggleRow({
  label,
  checked,
  onChange,
  children,
}: {
  label: string
  checked: boolean
  onChange: (on: boolean) => void
  children?: ReactNode
}) {
  return (
    <div className="space-y-3">
      <label className="flex items-center gap-2 text-sm">
        <Switch checked={checked} onCheckedChange={onChange} aria-label={label} />
        {label}
      </label>
      {children}
    </div>
  )
}

function VerdictSelect({ label, value, onChange }: { label: string; value: Verdict; onChange: (v: Verdict) => void }) {
  return (
    <label className="flex items-center gap-2 text-sm">
      {label}
      <NativeSelect aria-label={label} value={value} onChange={(e) => onChange(e.target.value as Verdict)}>
        {VERDICTS.map((v) => (
          <option key={v} value={v}>
            {v}
          </option>
        ))}
      </NativeSelect>
    </label>
  )
}

function PathChecklist({
  name,
  selected,
  onChange,
}: {
  name: string
  selected: string[]
  onChange: (paths: string[]) => void
}) {
  const extra = selected.filter((p) => !(CHECK_PATHS as readonly string[]).includes(p))
  const options = [...CHECK_PATHS, ...extra]
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1">
      {options.map((path) => {
        const id = `${name}-${path}`
        return (
          <label key={path} htmlFor={id} className="flex items-center gap-1.5 font-mono text-xs">
            <Checkbox
              id={id}
              checked={selected.includes(path)}
              onCheckedChange={(on) =>
                onChange(on ? [...selected, path] : selected.filter((p) => p !== path))
              }
            />
            {path}
          </label>
        )
      })}
    </div>
  )
}
