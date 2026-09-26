import { DownloadIcon, UploadIcon } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { downloadPolicyYaml, useActivatePolicy, useImportYaml, usePolicyVersions, useUpgradeCheck } from '@/features/policy/api'
import { ApiError } from '@/shared/api/problem'
import type { UpgradeReport } from '@/shared/api/types'
import { Button } from '@/shared/ui/button'
import { Input } from '@/shared/ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/shared/ui/table'
import { Textarea } from '@/shared/ui/textarea'

const errText = (err: unknown) =>
  err instanceof ApiError ? [err.message, ...err.fieldErrors.map((f) => `${f.field}: ${f.message}`)].join('\n') : String(err)

export function SettingsPage() {
  return (
    <div className="max-w-4xl space-y-8">
      <h1 className="text-xl font-semibold">Settings</h1>
      <PolicyVersions />
      <ExportImport />
      <UpgradeCheck />
      <section className="text-xs text-muted-foreground">
        API keys (TYPESAFE_API_KEY, ANTHROPIC_API_KEY) and the translator model come from the server environment (.env) and
        are never shown here.
      </section>
    </div>
  )
}

function PolicyVersions() {
  const versions = usePolicyVersions()
  const activate = useActivatePolicy()
  return (
    <section aria-label="Policy versions" className="space-y-2">
      <h2 className="text-sm font-semibold">Policy versions</h2>
      <p className="text-xs text-muted-foreground">
        Every change to the live set is an immutable snapshot. Activating an older one rolls back by re-pointing rules.
      </p>
      <Table data-testid="policy-versions">
        <TableHeader>
          <TableRow>
            <TableHead>Version</TableHead>
            <TableHead>Rules</TableHead>
            <TableHead>Note</TableHead>
            <TableHead>Hash</TableHead>
            <TableHead />
          </TableRow>
        </TableHeader>
        <TableBody>
          {versions.data?.length === 0 && (
            <TableRow>
              <TableCell colSpan={5} className="text-xs text-muted-foreground">
                Nothing published yet.
              </TableCell>
            </TableRow>
          )}
          {versions.data?.map((v) => (
            <TableRow key={v.version} data-testid={`policy-v${v.version}`}>
              <TableCell>v{v.version}</TableCell>
              <TableCell className="font-mono text-xs">{v.rules.map((r) => `${r.rule_id}@v${r.version}`).join(', ') || '—'}</TableCell>
              <TableCell className="text-xs">{v.note}</TableCell>
              <TableCell className="font-mono text-xs">{v.content_hash.slice(7, 15)}</TableCell>
              <TableCell>
                {v.active ? (
                  <span className="text-xs text-emerald-700">active</span>
                ) : (
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={activate.isPending}
                    onClick={() =>
                      activate.mutateAsync(v.version).then(
                        (pv) => toast.success(`Rolled back: policy v${pv.version} = v${v.version}`),
                        (e) => toast.error('Rollback failed', { description: errText(e) }),
                      )
                    }
                  >
                    Activate
                  </Button>
                )}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </section>
  )
}

function ExportImport() {
  const [text, setText] = useState('')
  const importYaml = useImportYaml()
  return (
    <section aria-label="Export and import" className="space-y-2">
      <h2 className="text-sm font-semibold">Export / import (YAML)</h2>
      <Button size="sm" variant="outline" onClick={() => downloadPolicyYaml().catch((e) => toast.error('Export failed', { description: errText(e) }))}>
        <DownloadIcon /> Export live rules
      </Button>
      <p className="text-xs text-muted-foreground">Import creates drafts only — nothing goes live until you publish it.</p>
      <input
        type="file"
        accept=".yaml,.yml,.json"
        aria-label="Import file"
        className="block text-xs"
        onChange={async (e) => setText((await e.target.files?.[0]?.text()) ?? '')}
      />
      <Textarea aria-label="Import YAML" rows={6} className="font-mono text-xs" placeholder="schema: 1&#10;rules: …" value={text} onChange={(e) => setText(e.target.value)} />
      <Button
        size="sm"
        disabled={!text.trim() || importYaml.isPending}
        onClick={() =>
          importYaml.mutateAsync(text).then(
            (r) => {
              toast.success(`Imported ${r.created.length} draft rule(s), ${r.tests_created} test case(s)`)
              setText('')
            },
            (e) => toast.error('Import failed', { description: errText(e) }),
          )
        }
      >
        <UploadIcon /> Import as drafts
      </Button>
    </section>
  )
}

function UpgradeCheck() {
  const [target, setTarget] = useState('jev-latest')
  const check = useUpgradeCheck()
  const [report, setReport] = useState<UpgradeReport | null>(null)
  return (
    <section aria-label="Jev upgrade check" className="space-y-2">
      <h2 className="text-sm font-semibold">Jev upgrade check</h2>
      <p className="text-xs text-muted-foreground">
        Runs every live rule's golden set on its pinned model and on the target, and lists verdict changes. Publishes nothing.
      </p>
      <div className="flex gap-2">
        <Input aria-label="Target Jev model" className="h-8 w-48 font-mono text-xs" value={target} onChange={(e) => setTarget(e.target.value)} />
        <Button
          size="sm"
          disabled={check.isPending}
          onClick={() => check.mutateAsync(target).then(setReport, (e) => toast.error('Upgrade check failed', { description: errText(e) }))}
        >
          {check.isPending ? 'Checking…' : 'Compare'}
        </Button>
      </div>
      {report && (
        <div className="space-y-1 text-xs" data-testid="upgrade-report">
          <p>
            {report.rules_checked} rule(s), {report.cases_checked} case(s): {report.current_pass} passing now → {report.target_pass} on{' '}
            <span className="font-mono">{report.target_model}</span> · {report.diffs.length} verdict change(s) · {report.jev_tokens} Jev tokens
          </p>
          {report.diffs.map((d, i) => (
            <p key={i} className="font-mono">
              {d.rule_id} · {d.test_case}: {d.current} ({d.current_values.join(', ')}) → {d.target} ({d.target_values.join(', ')}) · expected{' '}
              {d.expected}
            </p>
          ))}
        </div>
      )}
    </section>
  )
}
