import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from './client'
import { unwrap } from './problem'
import type { CheckRequest, EvaluateScope, TestCaseCreate } from './types'

export function useEvaluate() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (vars: { check_request: CheckRequest; scope: EvaluateScope }) =>
      unwrap(await api.POST('/api/evaluate', { body: vars })),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['playground', 'runs'] }),
  })
}

export function usePlaygroundRuns() {
  return useQuery({
    queryKey: ['playground', 'runs'],
    queryFn: async () => unwrap(await api.GET('/api/playground/runs', { params: { query: { limit: 20 } } })),
  })
}

export function useExamples() {
  return useQuery({
    queryKey: ['examples'],
    queryFn: async () => unwrap(await api.GET('/api/examples')),
    staleTime: Infinity,
  })
}

export function useLoadPack() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (name: string) =>
      unwrap(await api.POST('/api/examples/packs/{name}/load', { params: { path: { name } } })),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['rules'] }),
  })
}

export function useCreateTestCase() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (data: TestCaseCreate) => unwrap(await api.POST('/api/test-cases', { body: data })),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['test-cases'] }),
  })
}

export function useRuleTestCases(ruleId: string) {
  return useQuery({
    queryKey: ['test-cases', 'rule', ruleId],
    queryFn: async () =>
      unwrap(await api.GET('/api/rules/{rule_id}/test-cases', { params: { path: { rule_id: ruleId } } })),
  })
}
