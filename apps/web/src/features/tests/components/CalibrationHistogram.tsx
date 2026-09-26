import { useState } from 'react'
import type { Bands, Verdict } from '@/shared/api/types'

// Validated with the dataviz palette checker (light surface): CVD ΔE ≥ 12.5, contrast ≥ 3:1.
const COLORS: Record<Verdict, string> = { allow: '#0d9488', escalate: '#d97706', deny: '#be123c' }
const ORDER: Verdict[] = ['allow', 'escalate', 'deny']
const W = 600
const H = 170
const PAD = { l: 28, r: 8, t: 10, b: 24 }

interface Props {
  points: { value: number; expected: Verdict }[]
  range: [number, number]
  current: Bands
  suggested?: Bands | null
  bins?: number
}

/** Distribution of stored answers by expected verdict, over the current bands. */
export function CalibrationHistogram({ points, range, current, suggested, bins = 20 }: Props) {
  const [hover, setHover] = useState<number | null>(null)
  const [lo, hi] = range
  const span = hi - lo || 1
  const binOf = (v: number) => Math.min(bins - 1, Math.max(0, Math.floor(((v - lo) / span) * bins)))
  const counts = Array.from({ length: bins }, () => ({ allow: 0, escalate: 0, deny: 0 }))
  for (const p of points) counts[binOf(p.value)]![p.expected] += 1
  const maxCount = Math.max(1, ...counts.map((c) => c.allow + c.escalate + c.deny))
  const plotW = W - PAD.l - PAD.r
  const plotH = H - PAD.t - PAD.b
  const x = (v: number) => PAD.l + ((v - lo) / span) * plotW
  const y = (n: number) => PAD.t + plotH - (n / maxCount) * plotH
  const bw = plotW / bins

  // Dashed threshold lines; labels stack (row 0/1) and flip left near the right edge.
  const line = (v: number, label: string, key: string, row: number) => {
    const flip = x(v) > W * 0.7
    return (
      <g key={key}>
        <line x1={x(v)} x2={x(v)} y1={PAD.t} y2={PAD.t + plotH} stroke="currentColor" strokeWidth={2} strokeDasharray="4 3" />
        <text
          x={x(v) + (flip ? -4 : 4)}
          y={PAD.t + 10 + row * 12}
          textAnchor={flip ? 'end' : 'start'}
          className="fill-foreground text-[10px]"
        >
          {label} {v}
        </text>
      </g>
    )
  }

  return (
    <figure className="space-y-2" data-testid="calibration-histogram">
      <div className="relative">
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Distribution of test answers by expected verdict">
          {/* current bands, shaded behind the bars */}
          <rect x={x(lo)} y={PAD.t} width={x(current.escalate_at) - x(lo)} height={plotH} fill="#ccfbf1" opacity={0.5} />
          <rect x={x(current.escalate_at)} y={PAD.t} width={x(current.deny_at) - x(current.escalate_at)} height={plotH} fill="#fef3c7" opacity={0.6} />
          <rect x={x(current.deny_at)} y={PAD.t} width={x(hi) - x(current.deny_at)} height={plotH} fill="#ffe4e6" opacity={0.6} />
          <line x1={PAD.l} x2={W - PAD.r} y1={PAD.t + plotH} y2={PAD.t + plotH} className="stroke-muted-foreground/40" />
          {[lo, lo + span / 2, hi].map((t) => (
            <text key={t} x={x(t)} y={H - 6} textAnchor="middle" className="fill-muted-foreground text-[10px]">
              {Number(t.toFixed(2))}
            </text>
          ))}
          <text x={4} y={PAD.t + 8} className="fill-muted-foreground text-[10px]">
            {maxCount}
          </text>
          {counts.map((c, i) => {
            let acc = 0
            const bx = PAD.l + i * bw + 1
            return (
              <g key={i}>
                {ORDER.map((v) => {
                  const n = c[v]
                  if (!n) return null
                  const y0 = y(acc)
                  acc += n
                  const y1 = y(acc)
                  return (
                    <rect key={v} x={bx} y={y1 + 1} width={Math.max(1, bw - 2)} height={Math.max(1, y0 - y1 - 2)} rx={2} fill={COLORS[v]} />
                  )
                })}
                {/* hit target larger than the mark */}
                <rect
                  x={PAD.l + i * bw}
                  y={PAD.t}
                  width={bw}
                  height={plotH}
                  fill="transparent"
                  onMouseEnter={() => setHover(i)}
                  onMouseLeave={() => setHover(null)}
                />
              </g>
            )
          })}
          {suggested &&
            (suggested.escalate_at === suggested.deny_at
              ? line(suggested.deny_at, 'suggested escalate = deny', 'sed', 0)
              : [line(suggested.escalate_at, 'suggested escalate', 'se', 0), line(suggested.deny_at, 'suggested deny', 'sd', 1)])}
        </svg>
        {hover !== null && (
          <div
            className="pointer-events-none absolute top-0 rounded-md border bg-popover px-2 py-1 text-xs shadow"
            style={{ left: `${((PAD.l + hover * bw) / W) * 100}%` }}
            role="status"
          >
            {Number((lo + (hover * span) / bins).toFixed(2))}–{Number((lo + ((hover + 1) * span) / bins).toFixed(2))}:{' '}
            {ORDER.map((v) => `${counts[hover]![v]} ${v}`).join(' · ')}
          </div>
        )}
      </div>
      <figcaption className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
        {ORDER.map((v) => (
          <span key={v} className="flex items-center gap-1">
            <span className="inline-block size-2.5 rounded-sm" style={{ background: COLORS[v] }} /> expected {v}
          </span>
        ))}
        <span>· shaded: current bands (allow / escalate / deny)</span>
        {suggested && <span>· dashed: suggested thresholds</span>}
      </figcaption>
    </figure>
  )
}
