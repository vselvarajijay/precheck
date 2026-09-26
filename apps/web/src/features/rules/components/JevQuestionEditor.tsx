import { PlusIcon, XIcon } from 'lucide-react'
import type { JevQuestion } from '@/shared/api/types'
import { Button } from '@/shared/ui/button'
import { Input } from '@/shared/ui/input'
import { Textarea } from '@/shared/ui/textarea'
import { NativeSelect } from '@/shared/ui/native-select'
import {
  MAX_CHOICE_OPTIONS,
  MAX_SCORE_LEVELS,
  MIN_CHOICE_OPTIONS,
  MIN_SCORE_LEVELS,
  newQuestion,
  QUESTION_TYPES,
  type QuestionType,
} from '@/shared/lib/ruleBody'
import { FieldErrors } from './FieldErrors'

interface Props {
  qid: string
  value: JevQuestion
  onChange: (q: JevQuestion) => void
}

export function JevQuestionEditor({ qid, value: q, onChange }: Props) {
  const base = `jev.questions.${qid}`
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <label className="text-xs font-medium text-muted-foreground" htmlFor={`${qid}-type`}>
          Type
        </label>
        <NativeSelect
          id={`${qid}-type`}
          aria-label={`Question ${qid} type`}
          value={q.type}
          onChange={(e) => {
            const next = newQuestion(e.target.value as QuestionType)
            onChange({ ...next, instructions: q.instructions } as JevQuestion)
          }}
        >
          {QUESTION_TYPES.map((t) => (
            <option key={t} value={t}>
              {t === 'noul' ? 'noul (yes/no)' : t === 'choice' ? 'choice (pick one)' : 'score (rubric)'}
            </option>
          ))}
        </NativeSelect>
      </div>
      <div>
        <label className="text-xs font-medium text-muted-foreground" htmlFor={`${qid}-instructions`}>
          Question (instructions)
        </label>
        <Textarea
          id={`${qid}-instructions`}
          aria-label={`Question ${qid} instructions`}
          rows={2}
          value={q.instructions}
          placeholder="Does this refund send money to a different payment method than the original purchase?"
          onChange={(e) => onChange({ ...q, instructions: e.target.value })}
        />
        <FieldErrors path={`${base}.instructions`} />
      </div>
      {q.type === 'noul' && <NoulCriteriaEditor q={q} onChange={onChange} />}
      {q.type === 'choice' && <ChoiceCriteriaEditor q={q} onChange={onChange} />}
      {q.type === 'score' && <ScoreCriteriaEditor q={q} onChange={onChange} />}
      <FieldErrors path={`${base}.criteria`} />
    </div>
  )
}

function NoulCriteriaEditor({ q, onChange }: { q: Extract<JevQuestion, { type: 'noul' }>; onChange: (q: JevQuestion) => void }) {
  if (!q.criteria) {
    return (
      <Button type="button" variant="outline" size="sm" onClick={() => onChange({ ...q, criteria: { true: '', false: '' } })}>
        <PlusIcon /> Describe what true / false look like
      </Button>
    )
  }
  const c = q.criteria
  return (
    <div className="grid gap-2 sm:grid-cols-2">
      {(['true', 'false'] as const).map((k) => (
        <label key={k} className="text-xs text-muted-foreground">
          “{k}” means
          <Input
            aria-label={`Criteria ${k}`}
            value={c[k]}
            onChange={(e) => onChange({ ...q, criteria: { ...c, [k]: e.target.value } })}
          />
        </label>
      ))}
      <Button type="button" variant="ghost" size="sm" className="justify-self-start" onClick={() => onChange({ ...q, criteria: null })}>
        Remove criteria
      </Button>
    </div>
  )
}

function ChoiceCriteriaEditor({ q, onChange }: { q: Extract<JevQuestion, { type: 'choice' }>; onChange: (q: JevQuestion) => void }) {
  const entries = Object.entries(q.criteria)
  const atMax = entries.length >= MAX_CHOICE_OPTIONS
  const atMin = entries.length <= MIN_CHOICE_OPTIONS
  const setEntries = (next: [string, string][]) => onChange({ ...q, criteria: Object.fromEntries(next) })

  const addOption = () => {
    if (atMax) return
    let n = entries.length + 1
    while (q.criteria[`option_${n}`] !== undefined) n++
    setEntries([...entries, [`option_${n}`, '']])
  }

  return (
    <div className="space-y-2" data-testid="choice-criteria">
      <div className="text-xs font-medium text-muted-foreground">
        Options ({entries.length}/{MAX_CHOICE_OPTIONS})
      </div>
      {entries.map(([opt, desc], i) => (
        <div key={i} className="flex gap-2">
          <Input
            aria-label={`Option ${i + 1} name`}
            className="w-40 font-mono text-xs"
            value={opt}
            onChange={(e) => setEntries(entries.map((x, j) => (j === i ? [e.target.value, x[1]] : x)))}
          />
          <Input
            aria-label={`Option ${i + 1} description`}
            value={desc}
            onChange={(e) => setEntries(entries.map((x, j) => (j === i ? [x[0], e.target.value] : x)))}
          />
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            aria-label={`Remove option ${i + 1}`}
            disabled={atMin}
            onClick={() => setEntries(entries.filter((_, j) => j !== i))}
          >
            <XIcon />
          </Button>
        </div>
      ))}
      <Button type="button" variant="outline" size="sm" onClick={addOption} disabled={atMax}>
        <PlusIcon /> Add option
      </Button>
      {atMax && (
        <p className="text-xs text-amber-700" role="status">
          Jev allows at most {MAX_CHOICE_OPTIONS} options.
        </p>
      )}
    </div>
  )
}

function ScoreCriteriaEditor({ q, onChange }: { q: Extract<JevQuestion, { type: 'score' }>; onChange: (q: JevQuestion) => void }) {
  const levels = q.criteria
  const atMax = levels.length >= MAX_SCORE_LEVELS
  const atMin = levels.length <= MIN_SCORE_LEVELS
  return (
    <div className="space-y-2" data-testid="score-criteria">
      <div className="text-xs font-medium text-muted-foreground">
        Levels ({levels.length}/{MAX_SCORE_LEVELS}), lowest first
      </div>
      {levels.map((desc, i) => (
        <div key={i} className="flex items-center gap-2">
          <span className="w-6 text-right font-mono text-xs text-muted-foreground">{i}</span>
          <Input
            aria-label={`Level ${i} description`}
            value={desc}
            onChange={(e) => onChange({ ...q, criteria: levels.map((x, j) => (j === i ? e.target.value : x)) })}
          />
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            aria-label={`Remove level ${i}`}
            disabled={atMin}
            onClick={() => onChange({ ...q, criteria: levels.filter((_, j) => j !== i) })}
          >
            <XIcon />
          </Button>
        </div>
      ))}
      <Button
        type="button"
        variant="outline"
        size="sm"
        disabled={atMax}
        onClick={() => !atMax && onChange({ ...q, criteria: [...levels, ''] })}
      >
        <PlusIcon /> Add level
      </Button>
      {atMax && (
        <p className="text-xs text-amber-700" role="status">
          Jev allows at most {MAX_SCORE_LEVELS} levels.
        </p>
      )}
      {atMin && <p className="text-xs text-muted-foreground">A score needs at least {MIN_SCORE_LEVELS} levels.</p>}
    </div>
  )
}
