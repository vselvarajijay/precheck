import { ArrowLeftIcon } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'
import { toast } from 'sonner'
import { ApiError, errorsByPath } from '@/api/problem'
import { useRule, useRuleVersion, useSetRuleStatus, useUpdateRule } from '@/api/rules'
import type { RuleBody, RuleDetail, RuleStatus } from '@/api/types'
import { CheckBadges, GateBadge, StatusBadge } from '@/components/rules/badges'
import { PublishDialog } from '@/components/rules/PublishDialog'
import { RuleBodyEditor, type ValidationState } from '@/components/rules/RuleBodyEditor'
import { RuleTestsPanel } from '@/components/tests/RuleTestsPanel'
import { VersionDiff } from '@/components/rules/VersionDiff'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import { NativeSelect } from '@/components/ui-extra/native-select'
import { describePredicate } from '@/lib/ruleBody'

export function RuleDetailPage() {
  const { ruleId = '' } = useParams()
  const { data: rule, isPending, isError, error } = useRule(ruleId)

  if (isPending) return <Skeleton className="h-40 w-full" />
  if (isError) return <p className="text-sm text-destructive">Could not load rule: {error.message}</p>

  return (
    <div className="max-w-5xl space-y-4">
      <Link to="/rules" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:underline">
        <ArrowLeftIcon className="size-4" /> Rules
      </Link>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">{rule.name}</h1>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <span className="font-mono">{rule.id}</span>
            <GateBadge gate={rule.gate} />
            <StatusBadge status={rule.status} />
            <CheckBadges deterministic={rule.has_deterministic} jev={rule.has_jev} />
            <span>
              v{rule.current_version}
              {rule.live_version && rule.live_version !== rule.current_version && ` (live: v${rule.live_version})`}
            </span>
          </div>
        </div>
        <StatusActions rule={rule} />
      </div>
      <Tabs defaultValue="overview">
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="definition">Definition</TabsTrigger>
          <TabsTrigger value="versions">Versions ({rule.versions.length})</TabsTrigger>
          <TabsTrigger value="tests">Tests</TabsTrigger>
        </TabsList>
        <TabsContent value="overview" className="pt-2">
          <Overview rule={rule} />
        </TabsContent>
        <TabsContent value="definition" className="pt-2">
          <Definition key={rule.current.content_hash} rule={rule} />
        </TabsContent>
        <TabsContent value="versions" className="pt-2">
          <Versions rule={rule} />
        </TabsContent>
        <TabsContent value="tests" className="pt-2">
          <RuleTestsPanel rule={rule} />
        </TabsContent>
      </Tabs>
    </div>
  )
}

function StatusActions({ rule }: { rule: RuleDetail }) {
  const setStatus = useSetRuleStatus(rule.id)
  const run = async (status: RuleStatus, success: string) => {
    try {
      await setStatus.mutateAsync(status)
      toast.success(success)
    } catch (err) {
      const msgs = err instanceof ApiError ? err.fieldErrors.map((f) => `${f.field}: ${f.message}`) : []
      toast.error(err instanceof ApiError ? (err.problem?.title ?? err.message) : 'Status change failed', {
        description: msgs.join('\n') || (err as Error).message,
      })
    }
  }
  const busy = setStatus.isPending
  const livePending = rule.status === 'live' && rule.live_version !== rule.current_version
  return (
    <div className="flex flex-wrap gap-2">
      <PublishDialog
        rule={rule}
        canPublish={rule.status === 'draft' || livePending}
        label={livePending ? `Publish v${rule.current_version}` : 'Publish…'}
      />
      {rule.status === 'live' && (
        <Button variant="outline" disabled={busy} onClick={() => run('draft', 'Moved back to draft')}>
          Unpublish
        </Button>
      )}
      {rule.status !== 'archived' ? (
        <Button variant="ghost" disabled={busy} onClick={() => run('archived', 'Archived')}>
          Archive
        </Button>
      ) : (
        <Button variant="outline" disabled={busy} onClick={() => run('draft', 'Restored as draft')}>
          Restore
        </Button>
      )}
    </div>
  )
}

function Overview({ rule }: { rule: RuleDetail }) {
  const body = rule.current.body
  return (
    <dl className="grid gap-x-6 gap-y-3 text-sm sm:grid-cols-[180px_1fr]">
      <dt className="text-muted-foreground">Source text</dt>
      <dd>{rule.current.source_text ?? <em className="text-muted-foreground">none</em>}</dd>
      <dt className="text-muted-foreground">Explanation</dt>
      <dd>{rule.current.explanation ?? <em className="text-muted-foreground">none</em>}</dd>
      <dt className="text-muted-foreground">Applies when</dt>
      <dd className="font-mono text-xs">{body.applies_when ? describePredicate(body.applies_when) : 'always (at this gate)'}</dd>
      <dt className="text-muted-foreground">Required fields</dt>
      <dd className="font-mono text-xs">
        {body.requires?.length ? `${body.requires.join(', ')} (missing → ${body.on_missing})` : 'none'}
      </dd>
      {body.deterministic && (
        <>
          <dt className="text-muted-foreground">Deterministic</dt>
          <dd className="font-mono text-xs">
            {describePredicate(body.deterministic.predicate)} → {body.deterministic.verdict_when_true}
          </dd>
        </>
      )}
      {body.jev && (
        <>
          <dt className="text-muted-foreground">Jev ({body.jev.model})</dt>
          <dd className="space-y-1">
            {Object.entries(body.jev.questions).map(([qid, q]) => (
              <div key={qid}>
                <span className="font-mono text-xs">{qid}</span> <span className="text-xs">({q.type})</span>: {q.instructions}
              </div>
            ))}
            <div className="text-xs text-muted-foreground">Looks at: {body.jev.state_template.join(', ')}</div>
          </dd>
        </>
      )}
      <dt className="text-muted-foreground">Severity</dt>
      <dd>{body.severity}</dd>
      <dt className="text-muted-foreground">Provenance</dt>
      <dd className="text-xs text-muted-foreground">
        {rule.created_by === 'agent' ? 'proposed by agent' : 'created by user'}
        {rule.current.translator_model && ` · translator ${rule.current.translator_model} (${rule.current.prompt_version})`}
      </dd>
    </dl>
  )
}

function Definition({ rule }: { rule: RuleDetail }) {
  const update = useUpdateRule(rule.id)
  const [body, setBody] = useState<RuleBody>(rule.current.body)
  const [name, setName] = useState(rule.name)
  const [sourceText, setSourceText] = useState(rule.current.source_text ?? '')
  const [explanation, setExplanation] = useState(rule.current.explanation ?? '')
  const [errors, setErrors] = useState<Record<string, string[]>>({})
  const [validation, setValidation] = useState<ValidationState | null>(null)
  const readOnly = rule.status === 'archived'

  const save = async () => {
    try {
      const res = await update.mutateAsync({
        body,
        name,
        source_text: sourceText || null,
        explanation: explanation || null,
      })
      setErrors({})
      if (res.created_version) toast.success(`Saved as v${res.current_version}`)
      else toast.info('No changes — same content as the current version')
    } catch (err) {
      if (err instanceof ApiError) {
        setErrors(errorsByPath(err.fieldErrors, 'body.'))
        toast.error(err.problem?.title ?? 'Save failed', { description: err.message })
      } else toast.error('Save failed')
    }
  }

  return (
    <fieldset disabled={readOnly} className="space-y-4">
      {readOnly && <p className="text-sm text-muted-foreground">Archived rules are read-only. Restore to edit.</p>}
      <label className="block text-sm">
        Name
        <Input aria-label="Name" value={name} onChange={(e) => setName(e.target.value)} />
      </label>
      <label className="block text-sm">
        Source text
        <Textarea aria-label="Source text" rows={2} value={sourceText} onChange={(e) => setSourceText(e.target.value)} />
      </label>
      <label className="block text-sm">
        Explanation
        <Textarea aria-label="Explanation" rows={2} value={explanation} onChange={(e) => setExplanation(e.target.value)} />
      </label>
      <RuleBodyEditor value={body} onChange={setBody} errors={errors} onValidation={setValidation} />
      <div className="flex flex-wrap items-center gap-3">
        <Button onClick={save} disabled={update.isPending || readOnly}>
          {update.isPending ? 'Saving…' : 'Save new version'}
        </Button>
        <ValidationSummary v={validation} />
      </div>
    </fieldset>
  )
}

function ValidationSummary({ v }: { v: ValidationState | null }) {
  if (!v || v.checking) return <span className="text-xs text-muted-foreground">Checking…</span>
  if (!v.valid) return <span className="text-xs text-destructive">Has errors (see above)</span>
  return (
    <span className="text-xs text-muted-foreground" data-testid="validation-summary">
      Valid{v.liveProblems.length ? ` · not publishable yet: ${v.liveProblems.join('; ')}` : ' · publishable'}
    </span>
  )
}

function Versions({ rule }: { rule: RuleDetail }) {
  const nums = rule.versions.map((v) => v.version)
  const [to, setTo] = useState(nums.at(-1) ?? 1)
  const [from, setFrom] = useState(nums.at(-2) ?? nums[0] ?? 1)
  useEffect(() => {
    setTo(nums.at(-1) ?? 1)
    setFrom(nums.at(-2) ?? nums[0] ?? 1)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nums.length])
  const a = useRuleVersion(rule.id, from)
  const b = useRuleVersion(rule.id, to)

  return (
    <div className="space-y-3">
      <ul className="divide-y rounded-md border text-sm">
        {[...rule.versions].reverse().map((v) => (
          <li key={v.version} className="flex items-center gap-3 px-3 py-2">
            <span className="font-medium">v{v.version}</span>
            {v.is_current && <span className="text-xs text-muted-foreground">current</span>}
            {v.is_live && <span className="text-xs text-emerald-700">live</span>}
            <span className="font-mono text-xs text-muted-foreground">{v.content_hash.slice(7, 19)}</span>
            <span className="font-mono text-xs">{v.jev_model ?? ''}</span>
            <span className="ml-auto text-xs text-muted-foreground">
              {v.created_at ? new Date(`${v.created_at}Z`).toLocaleString() : ''}
            </span>
          </li>
        ))}
      </ul>
      {nums.length > 1 && (
        <div className="flex items-center gap-2 text-sm">
          Compare
          <NativeSelect aria-label="Compare from" value={from} onChange={(e) => setFrom(Number(e.target.value))}>
            {nums.map((n) => (
              <option key={n} value={n}>
                v{n}
              </option>
            ))}
          </NativeSelect>
          with
          <NativeSelect aria-label="Compare to" value={to} onChange={(e) => setTo(Number(e.target.value))}>
            {nums.map((n) => (
              <option key={n} value={n}>
                v{n}
              </option>
            ))}
          </NativeSelect>
        </div>
      )}
      {nums.length > 1 && a.data && b.data && <VersionDiff from={a.data} to={b.data} />}
    </div>
  )
}
