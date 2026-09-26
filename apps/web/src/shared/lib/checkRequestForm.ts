import type { CheckRequest, Gate } from '@/shared/api/types'

export type RequestKind = 'tool_call' | 'external_call' | 'content'

export interface HistoryRow {
  tool: string
  argsText: string
  result_summary: string
}

/** Editable, string-y form state for building a CheckRequest. */
export interface CheckRequestForm {
  gate: Gate
  agentId: string
  purpose: string
  userGoal: string
  history: HistoryRow[]
  kind: RequestKind
  tool: string
  argsText: string
  method: string
  url: string
  bodyText: string
  text: string
  reason: string
}

export function emptyForm(): CheckRequestForm {
  return {
    gate: 'tool_call',
    agentId: 'support-bot',
    purpose: 'Handles customer support for orders and refunds',
    userGoal: '',
    history: [],
    kind: 'tool_call',
    tool: '',
    argsText: '{}',
    method: 'POST',
    url: '',
    bodyText: '',
    text: '',
    reason: '',
  }
}

const pretty = (v: unknown) => JSON.stringify(v ?? {}, null, 2)

export function formFromRequest(cr: CheckRequest): CheckRequestForm {
  const r = cr.request
  return {
    gate: cr.gate,
    agentId: cr.agent?.id ?? '',
    purpose: cr.agent?.purpose ?? '',
    userGoal: cr.context?.user_goal ?? '',
    history: (cr.history ?? []).map((h) => ({
      tool: h.tool,
      argsText: pretty(h.args),
      result_summary: h.result_summary ?? '',
    })),
    kind: r.kind,
    tool: r.tool ?? '',
    argsText: pretty(r.args),
    method: r.method ?? 'POST',
    url: r.url ?? '',
    bodyText: typeof r.body === 'string' ? r.body : r.body == null ? '' : pretty(r.body),
    text: r.text ?? '',
    reason: cr.reason ?? '',
  }
}

function parseObject(text: string, label: string, errors: string[]): Record<string, unknown> | undefined {
  if (!text.trim()) return undefined
  try {
    const v = JSON.parse(text) as unknown
    if (v && typeof v === 'object' && !Array.isArray(v)) return v as Record<string, unknown>
    errors.push(`${label} must be a JSON object`)
  } catch (e) {
    errors.push(`${label}: ${(e as Error).message}`)
  }
  return undefined
}

/** Build the CheckRequest (blank optional fields are omitted) plus any form errors. */
export function requestFromForm(f: CheckRequestForm): { request: CheckRequest | null; errors: string[] } {
  const errors: string[] = []
  const agent = f.agentId || f.purpose ? { id: f.agentId || null, purpose: f.purpose || null } : null
  const history = f.history.map((h, i) => ({
    tool: h.tool,
    args: parseObject(h.argsText, `History #${i + 1} args`, errors) ?? {},
    result_summary: h.result_summary || null,
  }))
  history.forEach((h, i) => !h.tool && errors.push(`History #${i + 1} needs a tool name`))

  let request: CheckRequest['request']
  if (f.kind === 'tool_call') {
    if (!f.tool) errors.push('Tool name is required')
    request = { kind: 'tool_call', tool: f.tool, args: parseObject(f.argsText, 'Args', errors) ?? {} }
  } else if (f.kind === 'external_call') {
    if (!f.url) errors.push('URL is required')
    request = { kind: 'external_call', method: f.method || null, url: f.url, body: f.bodyText || null }
  } else {
    if (!f.text) errors.push('Content text is required')
    request = { kind: 'content', text: f.text }
  }

  const cr: CheckRequest = {
    gate: f.gate,
    agent,
    context: f.userGoal ? { user_goal: f.userGoal } : null,
    history: history.length ? history : null,
    request,
    reason: f.reason || null,
  }
  return { request: errors.length ? null : cr, errors }
}
