import type { Bands } from '@/shared/api/types'

export type BandRegion = 'allow' | 'escalate' | 'deny'

/** Which band a value falls in (inclusive thresholds, same rule as the engine). */
export function bandFor(value: number, bands: Bands): BandRegion {
  if (value >= bands.deny_at) return 'deny'
  if (value >= bands.escalate_at) return 'escalate'
  return 'allow'
}

interface Props {
  value: number
  bands: Bands
  min?: number
  max?: number
  /** e.g. "p", "1−p", "score" */
  label?: string
}

/** A value marker over the rule's allow / escalate / deny regions. */
export function ProbabilityBar({ value, bands, min = 0, max = 1, label = 'p' }: Props) {
  const span = max - min || 1
  const pct = (v: number) => Math.min(100, Math.max(0, ((v - min) / span) * 100))
  const region = bandFor(value, bands)
  return (
    <div className="flex items-center gap-2" data-testid="probability-bar" data-region={region}>
      <span className="w-20 shrink-0 font-mono text-xs tabular-nums">
        {label} {value.toFixed(2)}
      </span>
      <div
        className="relative h-3 flex-1 overflow-hidden rounded-sm"
        role="meter"
        aria-label={`${label} ${value.toFixed(2)} in ${region} band`}
        aria-valuemin={min}
        aria-valuemax={max}
        aria-valuenow={value}
      >
        <div data-part="allow" className="absolute inset-y-0 left-0 bg-emerald-200" style={{ width: `${pct(bands.escalate_at)}%` }} />
        <div
          data-part="escalate"
          className="absolute inset-y-0 bg-amber-200"
          style={{ left: `${pct(bands.escalate_at)}%`, width: `${pct(bands.deny_at) - pct(bands.escalate_at)}%` }}
        />
        <div data-part="deny" className="absolute inset-y-0 right-0 bg-red-200" style={{ left: `${pct(bands.deny_at)}%` }} />
        <div
          data-part="marker"
          className="absolute inset-y-0 w-0.5 -translate-x-1/2 bg-foreground"
          style={{ left: `${pct(value)}%` }}
        />
      </div>
      <span className="w-16 shrink-0 text-right text-xs text-muted-foreground">{region}</span>
    </div>
  )
}
