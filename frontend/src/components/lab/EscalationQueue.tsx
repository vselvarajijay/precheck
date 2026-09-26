import { toast } from 'sonner'
import { useEscalations, useResolveEscalation } from '@/api/lab'
import { ApiError } from '@/api/problem'
import type { Escalation, RuleInfo } from '@/api/types'
import { RuleResultCard } from '@/components/decision/RuleResultCard'
import { Button } from '@/components/ui/button'

export function EscalationQueue({ rules }: { rules: Record<string, RuleInfo> }) {
  const pending = useEscalations('pending')
  const resolve = useResolveEscalation()
  const act = async (e: Escalation, action: 'approve' | 'deny') => {
    try {
      await resolve.mutateAsync({ id: e.id, action })
      toast.success(action === 'approve' ? `Approved ${e.tool} — retry the step to use the grant` : `Denied ${e.tool}`)
    } catch (err) {
      toast.error('Could not resolve escalation', { description: err instanceof ApiError ? err.message : String(err) })
    }
  }
  const items = pending.data ?? []
  return (
    <section className="space-y-3" aria-label="Escalations">
      {pending.isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
      {!pending.isLoading && items.length === 0 && <p className="text-sm text-muted-foreground">No pending escalations.</p>}
      <ul className="space-y-3">
        {items.map((e) => (
          <li key={e.id} className="space-y-2 rounded-lg border p-3" data-testid={`escalation-item-${e.id}`}>
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div>
                <div className="font-mono text-sm font-medium">{e.tool}</div>
                <div className="font-mono text-[11px] text-muted-foreground">
                  session {e.session} · {e.created_at ? new Date(e.created_at + 'Z').toLocaleString() : ''}
                </div>
              </div>
              <div className="flex gap-2">
                <Button size="sm" onClick={() => act(e, 'approve')} disabled={resolve.isPending}>
                  Approve
                </Button>
                <Button size="sm" variant="outline" onClick={() => act(e, 'deny')} disabled={resolve.isPending}>
                  Deny
                </Button>
              </div>
            </div>
            {e.check_request && (
              <div className="space-y-1 text-xs">
                {e.check_request.reason && <p>Reason: “{e.check_request.reason}”</p>}
                <pre className="rounded bg-muted/50 p-2 whitespace-pre-wrap">{JSON.stringify(e.check_request.request, null, 2)}</pre>
              </div>
            )}
            {e.decision?.rule_results
              ?.filter((r) => r.matched)
              .map((r) => <RuleResultCard key={r.rule_id} result={r} rule={rules[r.rule_id]} />)}
          </li>
        ))}
      </ul>
    </section>
  )
}
