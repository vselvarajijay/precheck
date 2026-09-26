import { useState } from 'react'
import type { Clarification } from '@/api/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

interface Props {
  clarifications: Clarification[]
  blocking: boolean
  busy: boolean
  onSubmit: (answers: Record<string, string>) => void
}

export function ClarificationsPanel({ clarifications, blocking, busy, onSubmit }: Props) {
  const [answers, setAnswers] = useState<Record<string, string>>({})
  const [other, setOther] = useState<Record<string, string>>({})
  const complete = clarifications.every((c) => (answers[c.id] ?? '').trim())

  return (
    <section
      aria-label="Clarifications"
      className={blocking ? 'rounded-lg border border-amber-300 bg-amber-50/60 p-4' : 'rounded-lg border p-4'}
      data-testid="clarifications"
    >
      <h2 className="text-sm font-semibold">{blocking ? 'Clarifications needed' : 'Optional clarifications'}</h2>
      <p className="mb-3 text-xs text-muted-foreground">
        {blocking
          ? 'The translator could not turn part of this into rules without your answer.'
          : 'The translator chose safe defaults; answer these to refine the result.'}
      </p>
      <div className="space-y-4">
        {clarifications.map((c) => (
          <fieldset key={c.id} className="space-y-1.5">
            <legend className="text-sm font-medium">{c.question}</legend>
            <p className="text-xs text-muted-foreground">{c.why}</p>
            {c.options.map((opt) => (
              <label key={opt} className="flex items-center gap-2 text-sm">
                <input
                  type="radio"
                  name={`clar-${c.id}`}
                  checked={answers[c.id] === opt}
                  onChange={() => setAnswers({ ...answers, [c.id]: opt })}
                />
                {opt}
              </label>
            ))}
            <label className="flex items-center gap-2 text-sm">
              <input
                type="radio"
                name={`clar-${c.id}`}
                aria-label={`Other answer for ${c.id}`}
                checked={answers[c.id] !== undefined && answers[c.id] === other[c.id] && !c.options.includes(other[c.id] ?? '')}
                onChange={() => setAnswers({ ...answers, [c.id]: other[c.id] ?? '' })}
              />
              <Input
                aria-label={`Free-text answer for ${c.id}`}
                className="h-8"
                placeholder="Other…"
                value={other[c.id] ?? ''}
                onChange={(e) => {
                  setOther({ ...other, [c.id]: e.target.value })
                  setAnswers({ ...answers, [c.id]: e.target.value })
                }}
              />
            </label>
          </fieldset>
        ))}
      </div>
      <Button className="mt-4" size="sm" disabled={!complete || busy} onClick={() => onSubmit(answers)}>
        {busy ? 'Re-translating…' : 'Re-translate with answers'}
      </Button>
    </section>
  )
}
