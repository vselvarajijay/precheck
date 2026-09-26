import { LanguagesIcon, PlusIcon } from 'lucide-react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { type RuleFilters, useRules } from '@/api/rules'
import { GATES, type Gate, type RuleStatus } from '@/api/types'
import { CheckBadges, GateBadge, StatusBadge } from '@/components/rules/badges'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { NativeSelect } from '@/components/ui-extra/native-select'
import { useDebounced } from '@/hooks/useDebounced'

export function RulesPage() {
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const q = params.get('q') ?? ''
  const gate = (params.get('gate') || undefined) as Gate | undefined
  const status = (params.get('status') || undefined) as RuleFilters['status']
  const debouncedQ = useDebounced(q, 250)
  const { data, isPending, isError, error } = useRules({ q: debouncedQ, gate, status })

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    setParams(next, { replace: true })
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Rules</h1>
        <div className="flex gap-2">
          <Button asChild variant="outline">
            <Link to="/rules/new">
              <PlusIcon /> New rule (manual)
            </Link>
          </Button>
          <Button asChild>
            <Link to="/rules/translate">
              <LanguagesIcon /> New from business case
            </Link>
          </Button>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Input
          aria-label="Search rules"
          placeholder="Search name, id or source text"
          className="w-72"
          value={q}
          onChange={(e) => setParam('q', e.target.value)}
        />
        <NativeSelect aria-label="Filter by gate" value={gate ?? ''} onChange={(e) => setParam('gate', e.target.value)}>
          <option value="">All gates</option>
          {GATES.map((g) => (
            <option key={g} value={g}>
              {g}
            </option>
          ))}
        </NativeSelect>
        <NativeSelect aria-label="Filter by status" value={status ?? ''} onChange={(e) => setParam('status', e.target.value)}>
          <option value="">Active (draft + live)</option>
          {(['draft', 'live', 'archived'] as RuleStatus[]).map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
          <option value="all">All</option>
        </NativeSelect>
      </div>

      {isError && <p className="text-sm text-destructive">Could not load rules: {error.message}</p>}
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Rule</TableHead>
            <TableHead>Gate</TableHead>
            <TableHead>Applies to</TableHead>
            <TableHead>Checks</TableHead>
            <TableHead>Jev</TableHead>
            <TableHead>Status</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {isPending &&
            [0, 1, 2].map((i) => (
              <TableRow key={i}>
                <TableCell colSpan={6}>
                  <Skeleton className="h-5 w-full" />
                </TableCell>
              </TableRow>
            ))}
          {data?.length === 0 && (
            <TableRow>
              <TableCell colSpan={6} className="py-8 text-center text-sm text-muted-foreground">
                No rules match. Create one from a business case or by hand.
              </TableCell>
            </TableRow>
          )}
          {data?.map((r) => (
            <TableRow
              key={r.id}
              className="cursor-pointer"
              onClick={() => navigate(`/rules/${r.id}`)}
              data-testid={`rule-row-${r.id}`}
            >
              <TableCell>
                <Link to={`/rules/${r.id}`} className="font-medium hover:underline" onClick={(e) => e.stopPropagation()}>
                  {r.name}
                </Link>
                {r.created_by === 'agent' && (
                  <span className="ml-2 rounded bg-violet-100 px-1 text-[10px] text-violet-800">proposed by agent</span>
                )}
                <div className="max-w-md truncate text-xs text-muted-foreground" title={r.source_text ?? undefined}>
                  {r.source_text ?? r.id}
                </div>
              </TableCell>
              <TableCell>
                <GateBadge gate={r.gate} />
              </TableCell>
              <TableCell className="font-mono text-xs">{r.applies_to_tools.join(', ') || 'all'}</TableCell>
              <TableCell>
                <CheckBadges deterministic={r.has_deterministic} jev={r.has_jev} />
              </TableCell>
              <TableCell className="font-mono text-xs">{r.jev_model ?? '—'}</TableCell>
              <TableCell>
                <StatusBadge status={r.status} />
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
