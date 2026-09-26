import type { FieldError, Problem } from './types'

/** An API failure carrying the RFC 7807 problem body when the server sent one. */
export class ApiError extends Error {
  readonly status: number
  readonly problem: Problem | null

  constructor(status: number, problem: Problem | null, fallback = 'Request failed') {
    super(problem?.detail ?? problem?.title ?? fallback)
    this.status = status
    this.problem = problem
  }

  get fieldErrors(): FieldError[] {
    return this.problem?.errors ?? []
  }
}

function asProblem(body: unknown): Problem | null {
  if (body && typeof body === 'object' && 'title' in body && 'status' in body) {
    return body as Problem
  }
  return null
}

/** Unwrap an openapi-fetch result: return data or throw ApiError. */
export function unwrap<T>(result: { data?: T; error?: unknown; response: Response }): T {
  if (result.error !== undefined || result.data === undefined) {
    throw new ApiError(result.response.status, asProblem(result.error))
  }
  return result.data
}

/** Group field errors by path, optionally stripping a prefix (e.g. `body.`). */
export function errorsByPath(errors: FieldError[], stripPrefix = ''): Record<string, string[]> {
  const out: Record<string, string[]> = {}
  for (const e of errors) {
    const path = stripPrefix && e.field.startsWith(stripPrefix) ? e.field.slice(stripPrefix.length) : e.field
    ;(out[path] ??= []).push(e.message)
  }
  return out
}
