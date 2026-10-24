import { ApiError } from './client'

export const MIXED_SOURCE_TITLE = 'Cannot compare measured and simulated values'

function containsMixedCode(value: unknown, depth = 0): boolean {
  if (value === 'mixed_data_source') return true
  if (depth >= 3 || typeof value !== 'object' || value === null) return false
  const record = value as Record<string, unknown>
  return ['code', 'error', 'detail'].some(key => containsMixedCode(record[key], depth + 1))
}

function codeOf(error: ApiError): unknown {
  const body = error.body
  return typeof body === 'object' && body !== null ? (body as Record<string, unknown>).code : null
}

/** A roof without the before/after pair verification needs: missing data, not a failure. */
export function isMissingMeasurementError(error: unknown): boolean {
  return (
    error instanceof ApiError && error.status === 409 && codeOf(error) === 'missing_measurement'
  )
}

export function isMixedDataSourceError(error: unknown): boolean {
  return error instanceof ApiError && error.status === 409 && containsMixedCode(error.body)
}
