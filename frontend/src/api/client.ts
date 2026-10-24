import type { ApiResponse } from './types'
import { operatorToken } from './auth'

function baseUrl(configured: string | undefined, fallback: string): string {
  return (configured || fallback).replace(/\/+$/, '')
}

// The FastAPI backend, and the oracle's HTTP server that submits verifications on chain.
export const BASE_URL = baseUrl(import.meta.env.VITE_API_URL, 'http://localhost:8000')
export const ORACLE_URL = baseUrl(import.meta.env.VITE_ORACLE_URL, 'http://localhost:4020')

function serverMessage(body: unknown): string | undefined {
  const message =
    typeof body === 'object' && body !== null
      ? (body as Record<string, unknown>).message
      : undefined
  return typeof message === 'string' ? message : undefined
}

export class ApiError extends Error {
  readonly status: number
  readonly body: unknown
  constructor(status: number, body: unknown) {
    // Both servers answer errors as { code, message } with a message meant for the screen.
    super(serverMessage(body) ?? `API request failed (HTTP ${status}).`)
    this.name = 'ApiError'
    this.status = status
    this.body = body
  }
}

async function request<T>(base: string, path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  const token = operatorToken()
  if (token && init.method === 'POST') headers.set('X-API-Key', token)
  if (!headers.has('Accept')) headers.set('Accept', 'application/json')
  if (typeof init.body === 'string' && !headers.has('Content-Type'))
    headers.set('Content-Type', 'application/json')
  const response = await fetch(`${base}/${path.replace(/^\/+/, '')}`, { ...init, headers })
  const raw = await response.text()
  let body: unknown = raw || undefined
  if (raw && response.headers.get('content-type')?.includes('json')) {
    try {
      body = JSON.parse(raw)
    } catch {
      if (response.ok) throw new Error('The API returned invalid JSON.')
    }
  }
  if (!response.ok) throw new ApiError(response.status, body)
  return body as T
}

function client(base: string) {
  return {
    get: <T = ApiResponse>(path: string, init?: RequestInit) =>
      request<T>(base, path, { ...init, method: 'GET' }),
    post: <T = ApiResponse>(path: string, body: unknown, init?: RequestInit) =>
      request<T>(base, path, { ...init, method: 'POST', body: JSON.stringify(body) }),
    // The browser sets the multipart boundary itself, so no Content-Type is added here.
    upload: <T = ApiResponse>(path: string, form: FormData, init?: RequestInit) =>
      request<T>(base, path, { ...init, method: 'POST', body: form }),
  }
}

export const api = client(BASE_URL)
export const oracle = client(ORACLE_URL)
