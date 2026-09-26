import { diffLines } from 'diff'
import type { RuleVersion } from '@/shared/api/types'
import { cn } from '@/shared/lib/utils'

function render(v: RuleVersion): string {
  return JSON.stringify(
    { source_text: v.source_text, explanation: v.explanation, body: v.body },
    null,
    2,
  )
}

/** Line diff of two versions (body + source text + explanation). */
export function VersionDiff({ from, to }: { from: RuleVersion; to: RuleVersion }) {
  const parts = diffLines(render(from), render(to))
  const changed = parts.some((p) => p.added || p.removed)
  return (
    <div className="space-y-2" data-testid="version-diff">
      <div className="text-xs text-muted-foreground">
        v{from.version} → v{to.version} {changed ? '' : '(no differences)'}
      </div>
      <pre className="max-h-[480px] overflow-auto rounded-md border bg-muted/30 p-2 text-xs leading-5">
        {parts.map((p, i) => (
          <span
            key={i}
            className={cn(
              'block whitespace-pre-wrap',
              p.added && 'bg-emerald-100 text-emerald-900',
              p.removed && 'bg-red-100 text-red-900 line-through decoration-red-400/60',
            )}
            data-diff={p.added ? 'added' : p.removed ? 'removed' : 'same'}
          >
            {p.value
              .replace(/\n$/, '')
              .split('\n')
              .map((line) => `${p.added ? '+ ' : p.removed ? '- ' : '  '}${line}`)
              .join('\n')}
          </span>
        ))}
      </pre>
    </div>
  )
}
