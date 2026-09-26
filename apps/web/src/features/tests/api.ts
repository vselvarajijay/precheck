import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/shared/api/client'
import { unwrap } from '@/shared/api/problem'
import type { Bands } from '@/shared/api/types'

export function useTestRuns(ruleId: string | null) {
  return useQuery({
    queryKey: ['test-runs', ruleId],
    queryFn: async () => unwrap(await api.GET('/api/test-runs', { params: { query: { rule_id: ruleId ?? undefined, limit: 10 } } })),
  })
}

export function useTestRun(runId: string | null) {
  return useQuery({
    queryKey: ['test-run', runId],
    enabled: !!runId,
    queryFn: async () => unwrap(await api.GET('/api/test-runs/{run_id}', { params: { path: { run_id: runId ?? '' } } })),
  })
}

export function useRunTests() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (vars: { scope: 'rule' | 'policy'; rule_id?: string; rule_status: 'draft' | 'live' }) =>
      unwrap(await api.POST('/api/test-runs', { body: vars })),
    onSuccess: (run) => {
      qc.setQueryData(['test-run', run.id], run)
      qc.invalidateQueries({ queryKey: ['test-runs'] })
    },
  })
}

export function useGenerateTests(ruleId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () =>
      unwrap(await api.POST('/api/rules/{rule_id}/generate-tests', { params: { path: { rule_id: ruleId } } })),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['test-cases'] }),
  })
}

export function useDeleteTestCase() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (id: string) => {
      const res = await api.DELETE('/api/test-cases/{case_id}', { params: { path: { case_id: id } } })
      if (!res.response.ok) unwrap(res as never)
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['test-cases'] }),
  })
}

export function useCalibrate(ruleId: string) {
  return useMutation({
    mutationFn: async (runId: string | undefined) =>
      unwrap(
        await api.POST('/api/rules/{rule_id}/calibrate', {
          params: { path: { rule_id: ruleId }, query: { run_id: runId } },
        }),
      ),
  })
}

export function useApplyBands(ruleId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (bands: Record<string, Bands>) =>
      unwrap(await api.POST('/api/rules/{rule_id}/apply-bands', { params: { path: { rule_id: ruleId } }, body: { bands } })),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['rules'] }),
  })
}
