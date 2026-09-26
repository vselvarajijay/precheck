import { ChevronDownIcon, ChevronUpIcon, FlaskConicalIcon, SparklesIcon, XIcon } from 'lucide-react'
import { useState } from 'react'
import type { RuleSpec, TranslatedTest, TranslationWarning } from '@/api/types'
import { BandsSlider } from '@/components/rules/BandsSlider'
import { CheckBadges, GateBadge } from '@/components/rules/badges'
import { RuleBodyEditor } from '@/components/rules/RuleBodyEditor'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { CHECK_PATHS, describePredicate } from '@/lib/ruleBody'

interface Props {
  spec: RuleSpec
  warnings: TranslationWarning[]
  tests: TranslatedTest[]
  onChange: (spec: RuleSpec) => void
  onRemove: () => void
  onTry: () => void
  onRefine: (instruction: string) => Promise<void>
  refining: boolean
}

export function TranslatedRuleCard({ spec, warnings, tests, onChange, onRemove, onTry, onRefine, refining }: Props) {
  const [expanded, setExpanded] = useState(false)
  const [instruction, setInstruction] = useState('')
  const body = spec.body
  const jev = body.jev
  const setJev = (patch: Partial<NonNullable<typeof jev>>) => jev && onChange({ ...spec, body: { ...body, jev: { ...jev, ...patch } } })

  return (
    <article className="space-y-3 rounded-lg border p-4" data-testid={`translated-rule-${spec.id}`} aria-label={spec.name}>
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold">{spec.name}</h3>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <span className="font-mono">{spec.id}</span>
            <GateBadge gate={spec.gate} />
            <CheckBadges deterministic={!!body.deterministic} jev={!!jev} />
            <span>severity {body.severity}</span>
            <span>{tests.length} generated test{tests.length === 1 ? '' : 's'}</span>
          </div>
        </div>
        <div className="flex gap-1">
          <Button size="sm" variant="outline" onClick={onTry}>
            <FlaskConicalIcon /> Try in playground
          </Button>
          <Button size="icon-sm" variant="ghost" aria-label={`Remove ${spec.id}`} onClick={onRemove}>
            <XIcon />
          </Button>
        </div>
      </header>

      {spec.source_text && (
        <blockquote className="border-l-2 pl-3 text-sm italic text-muted-foreground">From: “{spec.source_text}”</blockquote>
      )}
      <p className="text-sm">
        <span className="text-muted-foreground">Means: </span>
        {spec.explanation}
      </p>
      <dl className="grid gap-x-4 gap-y-1 text-xs sm:grid-cols-[110px_1fr]">
        <dt className="text-muted-foreground">Applies when</dt>
        <dd className="font-mono">{body.applies_when ? describePredicate(body.applies_when) : 'every request at this gate'}</dd>
        {body.deterministic && (
          <>
            <dt className="text-muted-foreground">Code</dt>
            <dd className="font-mono">
              {describePredicate(body.deterministic.predicate)} → {body.deterministic.verdict_when_true}
            </dd>
          </>
        )}
        {(body.requires?.length ?? 0) > 0 && (
          <>
            <dt className="text-muted-foreground">Requires</dt>
            <dd className="font-mono">
              {body.requires?.join(', ')} (missing → {body.on_missing})
            </dd>
          </>
        )}
      </dl>

      {jev && (
        <div className="space-y-3 rounded-md bg-violet-50/50 p-3">
          <div>
            <div className="text-xs font-medium">Looks at (sent to Jev)</div>
            <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1">
              {[...new Set([...CHECK_PATHS, ...jev.state_template])].map((p) => (
                <label key={p} className="flex items-center gap-1 font-mono text-[11px]">
                  <Checkbox
                    aria-label={`${spec.id} looks at ${p}`}
                    checked={jev.state_template.includes(p)}
                    onCheckedChange={(on) =>
                      setJev({ state_template: on ? [...jev.state_template, p] : jev.state_template.filter((x) => x !== p) })
                    }
                  />
                  {p}
                </label>
              ))}
            </div>
          </div>
          {Object.entries(jev.questions).map(([qid, q]) => {
            const outcome = jev.outcomes[qid]
            return (
              <div key={qid} className="space-y-2">
                <label className="block text-xs">
                  <span className="font-mono">{qid}</span> ({q.type}) — question
                  <Textarea
                    aria-label={`${spec.id} question ${qid}`}
                    rows={2}
                    value={q.instructions}
                    onChange={(e) => setJev({ questions: { ...jev.questions, [qid]: { ...q, instructions: e.target.value } } })}
                  />
                </label>
                {outcome && 'bands' in outcome && (
                  <BandsSlider
                    value={outcome.bands}
                    min={0}
                    max={q.type === 'score' ? Math.max(1, q.criteria.length - 1) : 1}
                    step={q.type === 'score' ? 0.1 : 0.01}
                    label={outcome.type === 'noul' && outcome.direction === 'low_is_bad' ? '1 − P(true)' : q.type === 'score' ? 'expected score' : 'P(true)'}
                    onChange={(bands) => setJev({ outcomes: { ...jev.outcomes, [qid]: { ...outcome, bands } } })}
                  />
                )}
              </div>
            )
          })}
        </div>
      )}

      {warnings.length > 0 && (
        <ul className="space-y-0.5 rounded-md border border-amber-200 bg-amber-50 p-2 text-xs text-amber-900" data-testid={`warnings-${spec.id}`}>
          {warnings.map((w, i) => (
            <li key={i}>
              <span className="font-mono">{w.code}</span>: {w.message}
            </li>
          ))}
        </ul>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <Input
          aria-label={`Refine ${spec.id}`}
          className="h-8 flex-1"
          placeholder="Refine: e.g. “make this stricter for amounts under $50”"
          value={instruction}
          onChange={(e) => setInstruction(e.target.value)}
        />
        <Button
          size="sm"
          variant="outline"
          disabled={!instruction.trim() || refining}
          onClick={async () => {
            await onRefine(instruction)
            setInstruction('')
          }}
        >
          <SparklesIcon /> {refining ? 'Refining…' : 'Refine'}
        </Button>
        <Button size="sm" variant="ghost" onClick={() => setExpanded(!expanded)} aria-expanded={expanded}>
          {expanded ? <ChevronUpIcon /> : <ChevronDownIcon />} Full definition
        </Button>
      </div>
      {expanded && <RuleBodyEditor value={body} onChange={(b) => onChange({ ...spec, body: b })} />}
    </article>
  )
}
