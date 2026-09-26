import type {
  Bands,
  JevCheck,
  JevQuestion,
  Outcome,
  Predicate,
  RuleBody,
  Verdict,
} from '@/shared/api/types'

// Jev limits (docs.typesafe.ai/api) — mirrored from the backend schema.
export const MAX_CHOICE_OPTIONS = 255
export const MIN_CHOICE_OPTIONS = 1
export const MIN_SCORE_LEVELS = 2
export const MAX_SCORE_LEVELS = 10
export const QUESTION_ID_RE = /^[a-z](?:_?[a-z0-9]){0,63}$/

/** CheckRequest fields a rule can look at (state_template / requires / predicate paths). */
export const CHECK_PATHS = [
  'request',
  'request.tool',
  'request.args',
  'request.url',
  'request.method',
  'request.body',
  'request.text',
  'history',
  'reason',
  'agent.purpose',
  'agent.id',
  'context.user_goal',
  'context.recent_messages',
] as const

export const QUESTION_TYPES = ['noul', 'choice', 'score'] as const
export type QuestionType = (typeof QUESTION_TYPES)[number]

export function newQuestion(type: QuestionType): JevQuestion {
  switch (type) {
    case 'noul':
      return { type, instructions: '' }
    case 'choice':
      return { type, instructions: '', criteria: { option_a: '', option_b: '' } }
    case 'score':
      return { type, instructions: '', criteria: ['', ''] }
  }
}

export function defaultOutcome(q: JevQuestion): Outcome {
  switch (q.type) {
    case 'noul':
      return { type: 'noul', bands: { escalate_at: 0.4, deny_at: 0.7 }, direction: 'high_is_bad' }
    case 'choice':
      return {
        type: 'choice',
        map: Object.fromEntries(Object.keys(q.criteria).map((k) => [k, 'allow' as Verdict])),
        min_confidence: 0,
      }
    case 'score': {
      const top = q.criteria.length - 1
      return { type: 'score', bands: { escalate_at: Math.max(0, top - 1), deny_at: top }, min_confidence: 0 }
    }
  }
}

export function newJevCheck(): JevCheck {
  const q = newQuestion('noul')
  return { model: 'jev-latest', state_template: ['request'], questions: { q1: q }, outcomes: { q1: defaultOutcome(q) } }
}

export function emptyBody(): RuleBody {
  return { requires: [], on_missing: 'escalate', severity: 'medium', jev: newJevCheck() }
}

/** Keep a choice outcome's map aligned with the question's options (new ones default allow). */
export function syncOutcome(q: JevQuestion, o: Outcome | undefined): Outcome {
  if (!o || o.type !== q.type) return defaultOutcome(q)
  if (q.type === 'choice' && o.type === 'choice') {
    const map = Object.fromEntries(Object.keys(q.criteria).map((k) => [k, o.map[k] ?? ('allow' as Verdict)]))
    return { ...o, map }
  }
  if (q.type === 'score' && o.type === 'score') {
    const top = q.criteria.length - 1
    return { ...o, bands: clampBands(o.bands, 0, top) }
  }
  return o
}

export function clampBands(b: Bands, min: number, max: number): Bands {
  const c = (v: number) => Math.min(max, Math.max(min, v))
  const escalate_at = c(b.escalate_at)
  return { escalate_at, deny_at: Math.max(escalate_at, c(b.deny_at)) }
}

/** Instant client-side checks (the server remains the source of truth). */
export function localProblems(body: RuleBody): Record<string, string[]> {
  const out: Record<string, string[]> = {}
  const add = (path: string, msg: string) => (out[path] ??= []).push(msg)
  if (!body.deterministic && !body.jev) add('', 'A rule needs a deterministic check, a Jev check, or both.')
  const jev = body.jev
  if (jev) {
    if (Object.keys(jev.questions).length === 0) add('jev.questions', 'Add at least one question.')
    if (jev.state_template.length === 0) add('jev.state_template', 'Select at least one field for Jev to look at.')
    for (const [qid, q] of Object.entries(jev.questions)) {
      const base = `jev.questions.${qid}`
      if (!QUESTION_ID_RE.test(qid)) add(base, 'Question id: lowercase letters, digits, single underscores.')
      if (!q.instructions.trim()) add(`${base}.instructions`, 'Instructions are required.')
      if (q.type === 'choice') {
        const n = Object.keys(q.criteria).length
        if (n < MIN_CHOICE_OPTIONS) add(`${base}.criteria`, 'A choice needs at least 1 option.')
        if (n > MAX_CHOICE_OPTIONS) add(`${base}.criteria`, `A choice allows at most ${MAX_CHOICE_OPTIONS} options.`)
      }
      if (q.type === 'score') {
        const n = q.criteria.length
        if (n < MIN_SCORE_LEVELS || n > MAX_SCORE_LEVELS)
          add(`${base}.criteria`, `A score needs ${MIN_SCORE_LEVELS}–${MAX_SCORE_LEVELS} levels.`)
      }
      const o = jev.outcomes[qid]
      if (o && 'bands' in o && o.bands.escalate_at > o.bands.deny_at)
        add(`jev.outcomes.${qid}.bands`, 'Escalate threshold must not exceed the deny threshold.')
    }
  }
  return out
}

export function isPinned(model: string | null | undefined): boolean {
  return !!model && /^jev-\d+\.\d+\.\d+$/.test(model)
}

// --- predicates ----------------------------------------------------------------------------

export const PREDICATE_OPS = [
  { op: 'eq', label: 'equals' },
  { op: 'ne', label: 'not equals' },
  { op: 'gt', label: '>' },
  { op: 'gte', label: '>=' },
  { op: 'lt', label: '<' },
  { op: 'lte', label: '<=' },
  { op: 'in', label: 'is one of' },
  { op: 'not_in', label: 'is not one of' },
  { op: 'exists', label: 'exists' },
  { op: 'missing', label: 'is missing' },
  { op: 'regex', label: 'matches regex' },
  { op: 'min_len', label: 'min length' },
  { op: 'domain_in', label: 'domain in' },
  { op: 'domain_not_in', label: 'domain not in' },
  { op: 'all', label: 'ALL of' },
  { op: 'any', label: 'ANY of' },
  { op: 'not', label: 'NOT' },
] as const
export type PredicateOp = (typeof PREDICATE_OPS)[number]['op']

export function defaultPredicate(op: PredicateOp, path = 'request.tool'): Predicate {
  switch (op) {
    case 'eq':
    case 'ne':
      return { op, path, value: '' }
    case 'gt':
    case 'gte':
    case 'lt':
    case 'lte':
      return { op, path: path === 'request.tool' ? 'request.args.amount' : path, value: 0 }
    case 'in':
    case 'not_in':
      return { op, path, values: [''] }
    case 'exists':
    case 'missing':
      return { op, path }
    case 'regex':
      return { op, path, pattern: '.*' }
    case 'min_len':
      return { op, path: 'reason', value: 10 }
    case 'domain_in':
    case 'domain_not_in':
      return { op, path: 'request.url', domains: ['example.com'] }
    case 'all':
    case 'any':
      return { op, predicates: [{ op: 'eq', path, value: '' }] }
    case 'not':
      return { op, predicate: { op: 'eq', path, value: '' } }
  }
}

const SYMBOL: Record<string, string> = { eq: '==', ne: '!=', gt: '>', gte: '>=', lt: '<', lte: '<=' }

export function describePredicate(p: Predicate): string {
  switch (p.op) {
    case 'all':
    case 'any':
      return `(${p.predicates.map(describePredicate).join(p.op === 'all' ? ' AND ' : ' OR ')})`
    case 'not':
      return `NOT ${describePredicate(p.predicate)}`
    case 'exists':
      return `${p.path} exists`
    case 'missing':
      return `${p.path} is missing`
    case 'in':
    case 'not_in':
      return `${p.path} ${p.op === 'in' ? 'in' : 'not in'} [${p.values.map((v) => JSON.stringify(v)).join(', ')}]`
    case 'regex':
      return `${p.path} matches /${p.pattern}/`
    case 'min_len':
      return `len(${p.path}) >= ${p.value}`
    case 'domain_in':
    case 'domain_not_in':
      return `domain(${p.path}) ${p.op === 'domain_in' ? 'in' : 'not in'} [${p.domains.join(', ')}]`
    default:
      return `${p.path} ${SYMBOL[p.op]} ${JSON.stringify(p.value)}`
  }
}
