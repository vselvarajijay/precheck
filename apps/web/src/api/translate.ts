import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from './client'
import { ApiError, unwrap } from './problem'
import type { RuleSpec, SaveTranslation, TranslateInput, TranslateResponse } from './types'

export type TranslateStage = 'plan' | 'rules' | 'validating' | 'repairing' | 'tests'

type StreamEvent =
  | { type: 'progress'; stage: TranslateStage }
  | { type: 'result'; data: TranslateResponse }
  | { type: 'error'; status: number; detail: string }

/** POST /api/translate/stream and report progress as NDJSON events arrive. */
export async function translateStream(
  input: TranslateInput,
  onProgress: (stage: TranslateStage) => void,
): Promise<TranslateResponse> {
  const res = await globalThis.fetch(`${globalThis.location?.origin ?? ''}/api/translate/stream`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(input),
  })
  if (!res.ok || !res.body) {
    const problem = await res.json().catch(() => null)
    throw new ApiError(res.status, problem)
  }
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader()
  let buffer = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (value) buffer += value
    let nl: number
    while ((nl = buffer.indexOf('\n')) >= 0) {
      const line = buffer.slice(0, nl).trim()
      buffer = buffer.slice(nl + 1)
      if (!line) continue
      const event = JSON.parse(line) as StreamEvent
      if (event.type === 'progress') onProgress(event.stage)
      else if (event.type === 'result') return event.data
      else throw new ApiError(event.status, { type: 'about:blank', title: 'Translator unavailable', status: event.status, detail: event.detail })
    }
    if (done) break
  }
  throw new ApiError(502, { type: 'about:blank', title: 'Translation ended unexpectedly', status: 502 })
}

export function useAnswerClarifications(caseId: string | null) {
  return useMutation({
    mutationFn: async (answers: Record<string, string>) =>
      unwrap(
        await api.POST('/api/translate/{case_id}/answers', {
          params: { path: { case_id: caseId ?? '' } },
          body: { answers },
        }),
      ),
  })
}

export function useSaveTranslation(caseId: string | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (data: SaveTranslation) =>
      unwrap(
        await api.POST('/api/translate/{case_id}/save', { params: { path: { case_id: caseId ?? '' } }, body: data }),
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['rules'] })
      qc.invalidateQueries({ queryKey: ['test-cases'] })
    },
  })
}

export function useRefineRule() {
  return useMutation({
    mutationFn: async (vars: { rule: RuleSpec; instruction: string }) =>
      unwrap(await api.POST('/api/translate/refine', { body: vars })),
  })
}
