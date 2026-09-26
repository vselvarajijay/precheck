import { type KeyboardEvent, type PointerEvent, useRef } from 'react'
import type { Bands } from '@/shared/api/types'
import { Input } from '@/shared/ui/input'

interface Props {
  value: Bands
  onChange: (b: Bands) => void
  min?: number
  max?: number
  step?: number
  /** What the value means, e.g. "P(true)" or "expected score". */
  label?: string
}

type Thumb = 'escalate' | 'deny'

/** Two-thumb threshold editor: allow < escalate_at <= escalate < deny_at <= deny.
 *  Each thumb is bounded by the other, so escalate can never pass deny (no thumb swapping). */
export function BandsSlider({ value, onChange, min = 0, max = 1, step = 0.01, label = 'P(true)' }: Props) {
  const trackRef = useRef<HTMLDivElement>(null)
  const dragging = useRef<Thumb | null>(null)
  const span = max - min || 1
  const decimals = (String(step).split('.')[1] ?? '').length
  const round = (v: number) => Number((Math.round(v / step) * step).toFixed(decimals))
  const pct = (v: number) => `${((v - min) / span) * 100}%`

  const bounds = (t: Thumb): [number, number] =>
    t === 'escalate' ? [min, value.deny_at] : [value.escalate_at, max]

  const setThumb = (t: Thumb, raw: number) => {
    const [lo, hi] = bounds(t)
    const v = Math.min(hi, Math.max(lo, round(raw)))
    onChange(t === 'escalate' ? { ...value, escalate_at: v } : { ...value, deny_at: v })
  }

  const current = (t: Thumb) => (t === 'escalate' ? value.escalate_at : value.deny_at)

  const onKeyDown = (t: Thumb) => (e: KeyboardEvent) => {
    const big = step * 10
    const delta: Record<string, number> = {
      ArrowRight: step, ArrowUp: step, ArrowLeft: -step, ArrowDown: -step, PageUp: big, PageDown: -big,
    }
    if (e.key in delta) setThumb(t, current(t) + delta[e.key]!)
    else if (e.key === 'Home') setThumb(t, bounds(t)[0])
    else if (e.key === 'End') setThumb(t, bounds(t)[1])
    else return
    e.preventDefault()
  }

  const valueAt = (clientX: number) => {
    const rect = trackRef.current?.getBoundingClientRect()
    if (!rect || rect.width === 0) return min
    return min + ((clientX - rect.left) / rect.width) * span
  }

  const onPointerDown = (t: Thumb) => (e: PointerEvent<HTMLDivElement>) => {
    dragging.current = t
    e.currentTarget.setPointerCapture?.(e.pointerId)
    e.currentTarget.focus()
    e.preventDefault()
  }
  const onPointerMove = (e: PointerEvent<HTMLDivElement>) => {
    if (dragging.current) setThumb(dragging.current, valueAt(e.clientX))
  }
  const endDrag = () => {
    dragging.current = null
  }

  const thumb = (t: Thumb, ariaLabel: string) => {
    const [lo, hi] = bounds(t)
    return (
      <div
        role="slider"
        tabIndex={0}
        aria-label={ariaLabel}
        aria-valuemin={lo}
        aria-valuemax={hi}
        aria-valuenow={current(t)}
        aria-orientation="horizontal"
        data-thumb={t}
        onKeyDown={onKeyDown(t)}
        onPointerDown={onPointerDown(t)}
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
        className="absolute top-1/2 size-4 -translate-x-1/2 -translate-y-1/2 cursor-grab rounded-full border-2 border-foreground bg-background shadow outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
        style={{ left: pct(current(t)) }}
      />
    )
  }

  return (
    <div className="space-y-2" data-testid="bands-slider">
      <div className="relative h-5 touch-none select-none" ref={trackRef}>
        <div className="absolute inset-x-0 top-1/2 h-2 -translate-y-1/2 overflow-hidden rounded-full" aria-hidden>
          <div className="absolute inset-y-0 left-0 bg-emerald-300" style={{ width: pct(value.escalate_at) }} />
          <div
            className="absolute inset-y-0 bg-amber-300"
            style={{ left: pct(value.escalate_at), width: `calc(${pct(value.deny_at)} - ${pct(value.escalate_at)})` }}
          />
          <div className="absolute inset-y-0 right-0 bg-red-300" style={{ left: pct(value.deny_at) }} />
        </div>
        {thumb('escalate', 'Escalate threshold')}
        {thumb('deny', 'Deny threshold')}
      </div>
      <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
        <span className="text-emerald-700">allow &lt; {value.escalate_at}</span>
        <label className="flex items-center gap-1">
          escalate at
          <Input
            aria-label="Escalate at"
            type="number"
            className="h-7 w-20"
            min={min}
            max={value.deny_at}
            step={step}
            value={value.escalate_at}
            onChange={(ev) => ev.target.value !== '' && setThumb('escalate', Number(ev.target.value))}
          />
        </label>
        <label className="flex items-center gap-1">
          deny at
          <Input
            aria-label="Deny at"
            type="number"
            className="h-7 w-20"
            min={value.escalate_at}
            max={max}
            step={step}
            value={value.deny_at}
            onChange={(ev) => ev.target.value !== '' && setThumb('deny', Number(ev.target.value))}
          />
        </label>
        <span>on {label} · inclusive</span>
      </div>
    </div>
  )
}
