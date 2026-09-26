import { json } from '@codemirror/lang-json'
import CodeMirror, { EditorView } from '@uiw/react-codemirror'
import { PlusIcon, XIcon } from 'lucide-react'
import { GATES, type Gate } from '@/shared/api/types'
import { Button } from '@/shared/ui/button'
import { Input } from '@/shared/ui/input'
import { RadioGroup, RadioGroupItem } from '@/shared/ui/radio-group'
import { Textarea } from '@/shared/ui/textarea'
import { NativeSelect } from '@/shared/ui/native-select'
import type { CheckRequestForm, RequestKind } from '@/shared/lib/checkRequestForm'

interface Props {
  value: CheckRequestForm
  onChange: (f: CheckRequestForm) => void
}

const ARGS_EXTENSIONS = [json(), EditorView.lineWrapping, EditorView.contentAttributes.of({ 'aria-label': 'Args JSON' })]

const KINDS: { kind: RequestKind; label: string }[] = [
  { kind: 'tool_call', label: 'Tool call' },
  { kind: 'external_call', label: 'External call' },
  { kind: 'content', label: 'Content' },
]

export function ScenarioBuilder({ value: f, onChange }: Props) {
  const set = (patch: Partial<CheckRequestForm>) => onChange({ ...f, ...patch })
  return (
    <div className="space-y-3" data-testid="scenario-builder">
      <div className="grid grid-cols-[110px_1fr] items-center gap-2 text-sm">
        <label htmlFor="pg-gate">Gate</label>
        <NativeSelect id="pg-gate" aria-label="Gate" value={f.gate} onChange={(e) => set({ gate: e.target.value as Gate })}>
          {GATES.map((g) => (
            <option key={g} value={g}>
              {g}
            </option>
          ))}
        </NativeSelect>
        <label htmlFor="pg-agent">Agent</label>
        <Input id="pg-agent" aria-label="Agent id" value={f.agentId} onChange={(e) => set({ agentId: e.target.value })} />
        <label htmlFor="pg-purpose">Purpose</label>
        <Input id="pg-purpose" aria-label="Agent purpose" value={f.purpose} onChange={(e) => set({ purpose: e.target.value })} />
        <label htmlFor="pg-goal">User goal</label>
        <Input id="pg-goal" aria-label="User goal" value={f.userGoal} onChange={(e) => set({ userGoal: e.target.value })} />
      </div>

      <fieldset className="min-w-0 space-y-2 rounded-md border p-2">
        <legend className="px-1 text-xs font-medium">History (prior tool calls)</legend>
        {f.history.map((h, i) => (
          <div key={i} className="space-y-1 rounded bg-muted/40 p-2" data-testid={`history-${i}`}>
            <div className="flex gap-2">
              <Input
                aria-label={`History ${i + 1} tool`}
                className="h-8 font-mono text-xs"
                placeholder="lookup_order"
                value={h.tool}
                onChange={(e) => set({ history: f.history.map((x, j) => (j === i ? { ...x, tool: e.target.value } : x)) })}
              />
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                aria-label={`Remove history ${i + 1}`}
                onClick={() => set({ history: f.history.filter((_, j) => j !== i) })}
              >
                <XIcon />
              </Button>
            </div>
            <Textarea
              aria-label={`History ${i + 1} args`}
              rows={2}
              className="font-mono text-xs"
              value={h.argsText}
              onChange={(e) => set({ history: f.history.map((x, j) => (j === i ? { ...x, argsText: e.target.value } : x)) })}
            />
            <Input
              aria-label={`History ${i + 1} result summary`}
              className="h-8 text-xs"
              placeholder="Result summary, e.g. Order $620, paid with Visa 4242"
              value={h.result_summary}
              onChange={(e) =>
                set({ history: f.history.map((x, j) => (j === i ? { ...x, result_summary: e.target.value } : x)) })
              }
            />
          </div>
        ))}
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => set({ history: [...f.history, { tool: '', argsText: '{}', result_summary: '' }] })}
        >
          <PlusIcon /> Add prior call
        </Button>
      </fieldset>

      <fieldset className="min-w-0 space-y-2 rounded-md border p-2">
        <legend className="px-1 text-xs font-medium">Request</legend>
        <RadioGroup
          aria-label="Request kind"
          className="flex gap-4"
          value={f.kind}
          onValueChange={(k) => set({ kind: k as RequestKind })}
        >
          {KINDS.map(({ kind, label }) => (
            <label key={kind} className="flex items-center gap-1.5 text-sm">
              <RadioGroupItem value={kind} aria-label={label} />
              {label}
            </label>
          ))}
        </RadioGroup>
        {f.kind === 'tool_call' && (
          <div className="space-y-2" data-testid="tool-call-fields">
            <Input aria-label="Tool" className="font-mono text-sm" placeholder="issue_refund" value={f.tool} onChange={(e) => set({ tool: e.target.value })} />
            <div className="overflow-hidden rounded-md border text-xs" data-testid="args-editor">
              <CodeMirror value={f.argsText} height="110px" extensions={ARGS_EXTENSIONS} onChange={(argsText) => set({ argsText })} />
            </div>
          </div>
        )}
        {f.kind === 'external_call' && (
          <div className="space-y-2" data-testid="external-call-fields">
            <div className="flex gap-2">
              <NativeSelect aria-label="Method" value={f.method} onChange={(e) => set({ method: e.target.value })}>
                {['GET', 'POST', 'PUT', 'PATCH', 'DELETE'].map((m) => (
                  <option key={m}>{m}</option>
                ))}
              </NativeSelect>
              <Input aria-label="URL" className="font-mono text-xs" placeholder="https://…" value={f.url} onChange={(e) => set({ url: e.target.value })} />
            </div>
            <Textarea aria-label="Body" rows={3} className="font-mono text-xs" value={f.bodyText} onChange={(e) => set({ bodyText: e.target.value })} />
          </div>
        )}
        {f.kind === 'content' && (
          <Textarea aria-label="Content text" rows={4} data-testid="content-fields" value={f.text} onChange={(e) => set({ text: e.target.value })} />
        )}
      </fieldset>

      <label className="block text-sm">
        Reason (the agent's stated justification)
        <Textarea aria-label="Reason" rows={2} value={f.reason} onChange={(e) => set({ reason: e.target.value })} />
      </label>
    </div>
  )
}
