import { useState } from 'react'
import { toast } from 'sonner'
import { usePublish, useRuleDiff } from '@/api/policy'
import { ApiError } from '@/api/problem'
import type { PublishResult, RuleDetail, RuleVersion } from '@/api/types'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import { isPinned } from '@/lib/ruleBody'
import { VersionDiff } from './VersionDiff'

/** Publish = pin Jev, run the golden set on the pinned model, set live, snapshot policy. */
/** Stays mounted even when there is nothing left to publish, so the result stays visible
 *  after the rule refreshes; only the trigger button is hidden. */
export function PublishDialog({ rule, label, canPublish }: { rule: RuleDetail; label: string; canPublish: boolean }) {
  const [open, setOpen] = useState(false)
  const [result, setResult] = useState<PublishResult | null>(null)
  const diff = useRuleDiff(rule.id, open)
  const publish = usePublish(rule.id)
  const model = rule.current.body.jev?.model
  const draftRun = diff.data?.draft_run

  const run = async () => {
    try {
      const r = await publish.mutateAsync()
      setResult(r)
      toast.success(`Published ${rule.id} v${r.rule.live_version} · policy v${r.policy_version.version}`)
    } catch (err) {
      const msgs = err instanceof ApiError ? err.fieldErrors.map((f) => `${f.field}: ${f.message}`) : []
      toast.error(err instanceof ApiError ? (err.problem?.title ?? err.message) : 'Publish failed', {
        description: msgs.join('\n') || (err as Error).message,
      })
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        setOpen(o)
        if (!o) setResult(null)
      }}
    >
      {canPublish && (
        <DialogTrigger asChild>
          <Button>{label}</Button>
        </DialogTrigger>
      )}
      <DialogContent className="max-h-[90vh] overflow-auto sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>Publish {rule.name}</DialogTitle>
          <DialogDescription>
            Makes v{rule.current_version} the version enforcement uses and records a new policy version.
          </DialogDescription>
        </DialogHeader>
        {!result ? (
          <div className="space-y-4 text-sm" data-testid="publish-preview">
            {model && (
              <p>
                Jev model: <span className="font-mono">{model}</span>{' '}
                {isPinned(model) ? '(pinned)' : '— will be pinned to the concrete version Jev resolves it to, as a new version.'}
              </p>
            )}
            <p>
              Golden set:{' '}
              {draftRun
                ? `last draft run ${draftRun.pass_count}/${draftRun.pass_count + draftRun.fail_count + draftRun.error_count} passing`
                : 'no draft run yet'}{' '}
              · the tests run again on the pinned model during publish (failures warn, they don't block).
            </p>
            {diff.data?.live ? (
              <VersionDiff from={diff.data.live as RuleVersion} to={diff.data.draft as RuleVersion} />
            ) : (
              <p className="text-muted-foreground">Not live yet — nothing to diff against.</p>
            )}
          </div>
        ) : (
          <div className="space-y-2 text-sm" data-testid="publish-result">
            <p>
              Live: v{result.rule.live_version}
              {result.pinned_to && (
                <>
                  {' '}
                  · pinned <span className="font-mono">{result.pinned_from}</span> → <span className="font-mono">{result.pinned_to}</span>
                </>
              )}{' '}
              · policy v{result.policy_version.version}
            </p>
            {result.test_run && (
              <p>
                Tests on the pinned model: {result.test_run.pass_count}/{result.test_run.results?.length ?? 0} passing
              </p>
            )}
            {(result.warnings ?? []).map((w) => (
              <p key={w} className="rounded border border-amber-200 bg-amber-50 p-2 text-amber-900">
                ⚠ {w}
              </p>
            ))}
          </div>
        )}
        <DialogFooter>
          {!result ? (
            <Button onClick={run} disabled={publish.isPending}>
              {publish.isPending ? 'Publishing…' : `Publish v${rule.current_version}`}
            </Button>
          ) : (
            <Button variant="outline" onClick={() => setOpen(false)}>
              Done
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
