import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/shared/api/client'
import { ApiError, unwrap } from '@/shared/api/problem'

export function useRuleDiff(ruleId: string, enabled: boolean) {
  return useQuery({
    queryKey: ['rule-diff', ruleId],
    enabled,
    queryFn: async () => unwrap(await api.GET('/api/rules/{rule_id}/diff', { params: { path: { rule_id: ruleId } } })),
  })
}

export function usePublish(ruleId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () => unwrap(await api.POST('/api/rules/{rule_id}/publish', { params: { path: { rule_id: ruleId } } })),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['rules'] })
      qc.invalidateQueries({ queryKey: ['policy-versions'] })
      qc.invalidateQueries({ queryKey: ['test-runs'] })
      qc.invalidateQueries({ queryKey: ['rule-diff', ruleId] })
    },
  })
}

export function usePolicyVersions() {
  return useQuery({ queryKey: ['policy-versions'], queryFn: async () => unwrap(await api.GET('/api/policy-versions')) })
}

export function useActivatePolicy() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (version: number) =>
      unwrap(await api.POST('/api/policy-versions/{version}/activate', { params: { path: { version } } })),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['policy-versions'] })
      qc.invalidateQueries({ queryKey: ['rules'] })
    },
  })
}

export function useUpgradeCheck() {
  return useMutation({
    mutationFn: async (target_model: string) => unwrap(await api.POST('/api/jev/upgrade-check', { body: { target_model } })),
  })
}

export function useImportYaml() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (text: string) => unwrap(await api.POST('/api/import', { body: { yaml: text } })),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['rules'] }),
  })
}

/** Fetch the policy YAML (plain text) and hand it to the browser as a download. */
export async function downloadPolicyYaml() {
  const res = await globalThis.fetch(`${globalThis.location?.origin ?? ''}/api/export`)
  if (!res.ok) throw new ApiError(res.status, await res.json().catch(() => null))
  const blob = new Blob([await res.text()], { type: 'application/yaml' })
  const url = URL.createObjectURL(blob)
  const a = Object.assign(document.createElement('a'), { href: url, download: 'policy.yaml' })
  a.click()
  URL.revokeObjectURL(url)
}
