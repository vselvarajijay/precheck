import type { RuleSummary } from '@/shared/api/types'

export function ruleSummary(over: Partial<RuleSummary> = {}): RuleSummary {
  return {
    id: 'refund-over-limit',
    name: 'Refund over limit',
    gate: 'tool_call',
    status: 'live',
    created_by: 'user',
    current_version: 2,
    live_version: 2,
    source_text: 'Refunds over $500 need a manager.',
    severity: 'medium',
    has_deterministic: true,
    has_jev: false,
    jev_model: null,
    requires: ['request.args.amount'],
    applies_to_tools: ['issue_refund'],
    updated_at: '2026-09-26T08:00:00',
    ...over,
  }
}
