import type { Gate, RuleStatus, Verdict } from '@/api/types'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

const VERDICT_STYLE: Record<Verdict, string> = {
  allow: 'bg-emerald-100 text-emerald-800 border-emerald-200',
  escalate: 'bg-amber-100 text-amber-900 border-amber-200',
  deny: 'bg-red-100 text-red-800 border-red-200',
}

export function VerdictBadge({ verdict, className }: { verdict: Verdict; className?: string }) {
  return (
    <Badge variant="outline" className={cn('uppercase', VERDICT_STYLE[verdict], className)}>
      {verdict}
    </Badge>
  )
}

export function StatusBadge({ status }: { status: RuleStatus }) {
  const style =
    status === 'live'
      ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
      : status === 'archived'
        ? 'text-muted-foreground'
        : ''
  return (
    <Badge variant="outline" className={style}>
      {status === 'live' ? '● live' : status === 'draft' ? '○ draft' : 'archived'}
    </Badge>
  )
}

export function GateBadge({ gate }: { gate: Gate }) {
  return (
    <Badge variant="secondary" className="font-mono text-[11px]">
      {gate}
    </Badge>
  )
}

export function CheckBadges({ deterministic, jev }: { deterministic: boolean; jev: boolean }) {
  return (
    <span className="inline-flex gap-1">
      {deterministic && (
        <Badge variant="outline" className="font-mono text-[11px]">
          code
        </Badge>
      )}
      {jev && (
        <Badge variant="outline" className="border-violet-200 bg-violet-50 font-mono text-[11px] text-violet-800">
          jev
        </Badge>
      )}
    </span>
  )
}
