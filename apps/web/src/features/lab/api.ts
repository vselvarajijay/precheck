import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { api } from '@/shared/api/client'
import { unwrap } from '@/shared/api/problem'
import type { LabRun, RunStep } from '@/shared/api/types'

export function useScenarios() {
  return useQuery({ queryKey: ['lab', 'scenarios'], queryFn: async () => unwrap(await api.GET('/api/lab/scenarios')), staleTime: Infinity })
}

export function useLabRuns(scenarioId?: string) {
  return useQuery({
    queryKey: ['lab', 'runs', scenarioId ?? null],
    queryFn: async () => unwrap(await api.GET('/api/lab/runs', { params: { query: { scenario_id: scenarioId, limit: 50 } } })),
    refetchInterval: 5_000,
  })
}

export function useLabRun(runId: string | null) {
  return useQuery({
    queryKey: ['lab', 'run', runId],
    enabled: !!runId,
    queryFn: async () => unwrap(await api.GET('/api/lab/runs/{run_id}', { params: { path: { run_id: runId ?? '' } } })),
  })
}

export async function fetchLabRun(runId: string): Promise<LabRun> {
  return unwrap(await api.GET('/api/lab/runs/{run_id}', { params: { path: { run_id: runId } } }))
}

export function useStartRun() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: { mode: 'scripted' | 'llm'; scenario_id?: string | null; goal?: string | null; agent_id?: string | null }) =>
      unwrap(await api.POST('/api/lab/runs/start', { body: { scenario_id: null, goal: null, agent_id: null, ...body } })),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['lab', 'runs'] }),
  })
}

export function useRetryStep(runId: string) {
  return useMutation({
    mutationFn: async (index: number) =>
      unwrap(await api.POST('/api/lab/runs/{run_id}/retry/{index}', { params: { path: { run_id: runId, index } } })),
  })
}

export function useEscalations(status?: 'pending' | 'approved' | 'denied' | 'consumed') {
  return useQuery({
    queryKey: ['lab', 'escalations', status ?? 'all'],
    queryFn: async () => unwrap(await api.GET('/api/lab/escalations', { params: { query: { status } } })),
    refetchInterval: 3_000,
  })
}

export function useResolveEscalation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (vars: { id: string; action: 'approve' | 'deny' }) =>
      unwrap(
        await api.POST('/api/lab/escalations/{escalation_id}/{action}', {
          params: { path: { escalation_id: vars.id, action: vars.action } },
        }),
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['lab', 'escalations'] }),
  })
}

export function useLivePolicy() {
  return useQuery({ queryKey: ['lab', 'live-policy'], queryFn: async () => unwrap(await api.GET('/api/lab/live-policy')) })
}

export interface RunStream {
  steps: RunStep[]
  done: LabRun | null
  error: string | null
}

/** Live steps of a run over SSE (the server sends a catch-up first, so reconnects are safe). */
export function useRunEvents(runId: string | null): RunStream {
  const [state, setState] = useState<RunStream & { runId: string | null }>({ runId: null, ...EMPTY })
  useEffect(() => {
    if (!runId) return
    const update = (f: (s: RunStream) => Partial<RunStream>) =>
      setState((s) => {
        const cur = s.runId === runId ? s : { runId, ...EMPTY }
        return { ...cur, ...f(cur) }
      })
    const source = new EventSource(`/api/lab/runs/${encodeURIComponent(runId)}/events`)
    source.addEventListener('step', (e) => {
      const step = JSON.parse((e as MessageEvent).data) as RunStep
      update((s) => ({ steps: [...s.steps.filter((x) => x.index !== step.index), step].sort((a, b) => a.index - b.index) }))
    })
    source.addEventListener('done', (e) => {
      const run = JSON.parse((e as MessageEvent).data) as LabRun
      update((s) => ({ done: run, steps: run.steps?.length ? run.steps : s.steps }))
      source.close()
    })
    source.addEventListener('error', (e) => {
      // Without data this is a dropped connection: EventSource reconnects by itself.
      const data = (e as MessageEvent).data
      if (data) {
        update(() => ({ error: JSON.parse(data).detail ?? 'stream error' }))
        source.close()
      }
    })
    return () => source.close()
  }, [runId])
  return state.runId === runId && runId ? state : EMPTY
}

const EMPTY: RunStream = { steps: [], done: null, error: null }
