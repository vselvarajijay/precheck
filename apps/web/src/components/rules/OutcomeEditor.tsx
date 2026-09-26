import type { JevQuestion, Outcome, Verdict } from '@/api/types'
import { VERDICTS } from '@/api/types'
import { Input } from '@/components/ui/input'
import { NativeSelect } from '@/components/ui-extra/native-select'
import { BandsSlider } from './BandsSlider'
import { FieldErrors } from './FieldErrors'

interface Props {
  qid: string
  question: JevQuestion
  value: Outcome
  onChange: (o: Outcome) => void
}

export function OutcomeEditor({ qid, question, value: o, onChange }: Props) {
  return (
    <div className="space-y-3 rounded-md bg-muted/40 p-3">
      <div className="text-xs font-medium">How the answer maps to a verdict</div>
      {o.type === 'noul' && (
        <>
          <BandsSlider
            value={o.bands}
            onChange={(bands) => onChange({ ...o, bands })}
            label={o.direction === 'low_is_bad' ? '1 − P(true)' : 'P(true)'}
          />
          <label className="flex items-center gap-2 text-xs text-muted-foreground">
            Bad answer is
            <NativeSelect
              aria-label={`Question ${qid} direction`}
              value={o.direction ?? 'high_is_bad'}
              onChange={(e) => onChange({ ...o, direction: e.target.value as 'high_is_bad' | 'low_is_bad' })}
            >
              <option value="high_is_bad">true (high probability is bad)</option>
              <option value="low_is_bad">false (low probability is bad)</option>
            </NativeSelect>
          </label>
        </>
      )}
      {o.type === 'choice' && question.type === 'choice' && (
        <div className="space-y-2">
          {Object.keys(question.criteria).map((opt) => (
            <label key={opt} className="flex items-center gap-2 text-xs">
              <span className="w-40 truncate font-mono">{opt}</span>→
              <NativeSelect
                aria-label={`Verdict for ${opt}`}
                value={o.map[opt] ?? 'allow'}
                onChange={(e) => onChange({ ...o, map: { ...o.map, [opt]: e.target.value as Verdict } })}
              >
                {VERDICTS.map((v) => (
                  <option key={v} value={v}>
                    {v}
                  </option>
                ))}
              </NativeSelect>
            </label>
          ))}
          <MinConfidence value={o.min_confidence ?? 0} onChange={(min_confidence) => onChange({ ...o, min_confidence })} />
        </div>
      )}
      {o.type === 'score' && question.type === 'score' && (
        <>
          <BandsSlider
            value={o.bands}
            onChange={(bands) => onChange({ ...o, bands })}
            min={0}
            max={Math.max(1, question.criteria.length - 1)}
            step={0.1}
            label="expected score"
          />
          <MinConfidence value={o.min_confidence ?? 0} onChange={(min_confidence) => onChange({ ...o, min_confidence })} />
        </>
      )}
      <FieldErrors path={`jev.outcomes.${qid}`} />
    </div>
  )
}

function MinConfidence({ value, onChange }: { value: number; onChange: (v: number) => void }) {
  return (
    <label className="flex items-center gap-2 text-xs text-muted-foreground">
      Escalate when confidence below
      <Input
        aria-label="Minimum confidence"
        type="number"
        className="h-7 w-20"
        min={0}
        max={1}
        step={0.05}
        value={value}
        onChange={(e) => onChange(Math.min(1, Math.max(0, Number(e.target.value))))}
      />
    </label>
  )
}
