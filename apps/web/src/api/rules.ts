import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from './client'
import { unwrap } from './problem'
import type { Gate, RuleBody, RuleCreate, RuleStatus, RuleUpdate } from './types'

export interface RuleFilters {
  gate?: Gate
  status?: RuleStatus | 'all'
  q?: string
}

export const ruleKeys = {
  all: ['rules'] as const,
  list: (f: RuleFilters) => ['rules', 'list', f] as const,
  detail: (id: string) => ['rules', 'detail', id] as const,
  version: (id: string, n: number) => ['rules', 'version', id, n] as const,
}

export function useRules(filters: RuleFilters = {}) {
  return useQuery({
    queryKey: ruleKeys.list(filters),
    queryFn: async () =>
      unwrap(
        await api.GET('/api/rules', {
          params: { query: { gate: filters.gate, status: filters.status, q: filters.q || undefined } },
        }),
      ),
  })
}

export function useRule(id: string) {
  return useQuery({
    queryKey: ruleKeys.detail(id),
    queryFn: async () =>
      unwrap(await api.GET('/api/rules/{rule_id}', { params: { path: { rule_id: id } } })),
  })
}

export function useRuleVersion(id: string, version: number | null) {
  return useQuery({
    queryKey: ruleKeys.version(id, version ?? 0),
    enabled: version !== null,
    queryFn: async () =>
      unwrap(
        await api.GET('/api/rules/{rule_id}/versions/{version}', {
          params: { path: { rule_id: id, version: version ?? 0 } },
        }),
      ),
  })
}

function useInvalidateRules() {
  const qc = useQueryClient()
  return () => qc.invalidateQueries({ queryKey: ruleKeys.all })
}

export function useCreateRule() {
  const invalidate = useInvalidateRules()
  return useMutation({
    mutationFn: async (data: RuleCreate) => unwrap(await api.POST('/api/rules', { body: data })),
    onSuccess: invalidate,
  })
}

export function useUpdateRule(id: string) {
  const invalidate = useInvalidateRules()
  return useMutation({
    mutationFn: async (data: RuleUpdate) =>
      unwrap(await api.PUT('/api/rules/{rule_id}', { params: { path: { rule_id: id } }, body: data })),
    onSuccess: invalidate,
  })
}

export function useSetRuleStatus(id: string) {
  const invalidate = useInvalidateRules()
  return useMutation({
    mutationFn: async (status: RuleStatus) =>
      unwrap(
        await api.POST('/api/rules/{rule_id}/status', {
          params: { path: { rule_id: id } },
          body: { status },
        }),
      ),
    onSuccess: invalidate,
  })
}

/** Server-side validation of a rule body (the source of truth for the editor). */
export async function validateRuleBody(body: RuleBody) {
  return unwrap(await api.POST('/api/validate/rule-body', { body }))
}
