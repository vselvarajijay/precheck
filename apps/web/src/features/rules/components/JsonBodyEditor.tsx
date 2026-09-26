import { json } from '@codemirror/lang-json'
import CodeMirror, { EditorView } from '@uiw/react-codemirror'
import { useEffect, useRef, useState } from 'react'
import { validateRuleBody } from '@/features/rules/api'
import type { RuleBody } from '@/shared/api/types'

interface Props {
  value: RuleBody
  onApply: (body: RuleBody) => void
}

const EXTENSIONS = [json(), EditorView.contentAttributes.of({ 'aria-label': 'Rule body JSON' })]

type Status = { kind: 'synced' } | { kind: 'checking' } | { kind: 'error'; messages: string[] }

/** Raw JSON view of the rule body. Edits apply to the form only when they parse and pass
 *  server validation, so the form never sees a malformed body. */
export function JsonBodyEditor({ value, onApply }: Props) {
  const pretty = JSON.stringify(value, null, 2)
  const [text, setText] = useState(pretty)
  const [status, setStatus] = useState<Status>({ kind: 'synced' })
  const lastApplied = useRef(pretty)

  // Form -> JSON when the form changed and the user has no pending JSON edits.
  useEffect(() => {
    if (pretty !== lastApplied.current && status.kind === 'synced') {
      setText(pretty)
      lastApplied.current = pretty
    }
  }, [pretty, status.kind])

  useEffect(() => {
    if (text === lastApplied.current) return
    let parsed: RuleBody
    try {
      parsed = JSON.parse(text) as RuleBody
    } catch (e) {
      setStatus({ kind: 'error', messages: [`Invalid JSON: ${(e as Error).message}`] })
      return
    }
    setStatus({ kind: 'checking' })
    let cancelled = false
    const t = setTimeout(async () => {
      try {
        const r = await validateRuleBody(parsed)
        if (cancelled) return
        if (!r.valid) {
          setStatus({ kind: 'error', messages: r.errors.map((f) => `${f.field}: ${f.message}`) })
          return
        }
        lastApplied.current = JSON.stringify(parsed, null, 2)
        setStatus({ kind: 'synced' })
        onApply(parsed)
      } catch (e) {
        if (!cancelled) setStatus({ kind: 'error', messages: [(e as Error).message] })
      }
    }, 300)
    return () => {
      cancelled = true
      clearTimeout(t)
    }
  }, [text, onApply])

  return (
    <div className="space-y-2">
      <div className="overflow-hidden rounded-md border text-xs" data-testid="json-editor">
        <CodeMirror value={text} height="420px" extensions={EXTENSIONS} onChange={setText} />
      </div>
      <div className="text-xs" role="status" data-testid="json-status">
        {status.kind === 'synced' && <span className="text-emerald-700">In sync with the form.</span>}
        {status.kind === 'checking' && <span className="text-muted-foreground">Validating…</span>}
        {status.kind === 'error' && (
          <ul className="space-y-0.5 text-destructive">
            {status.messages.map((m) => (
              <li key={m}>{m}</li>
            ))}
            <li className="text-muted-foreground">Not applied to the form until valid.</li>
          </ul>
        )}
      </div>
    </div>
  )
}
