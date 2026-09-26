import { createContext, useContext } from 'react'

/** Errors keyed by RuleBody path (e.g. `jev.questions.q1.criteria`). */
export const FieldErrorsContext = createContext<Record<string, string[]>>({})

/** Messages for `path` and anything nested under it. */
export function useFieldErrors(path: string): string[] {
  const errors = useContext(FieldErrorsContext)
  return Object.entries(errors)
    .filter(([p]) => p === path || p.startsWith(`${path}.`))
    .flatMap(([, msgs]) => msgs)
}

export function FieldErrors({ path, exact = false }: { path: string; exact?: boolean }) {
  const all = useContext(FieldErrorsContext)
  const nested = useFieldErrors(path)
  const msgs = exact ? (all[path] ?? []) : nested
  if (msgs.length === 0) return null
  return (
    <ul className="mt-1 space-y-0.5 text-xs text-destructive" role="alert" data-testid={`errors-${path}`}>
      {[...new Set(msgs)].map((m) => (
        <li key={m}>{m}</li>
      ))}
    </ul>
  )
}
