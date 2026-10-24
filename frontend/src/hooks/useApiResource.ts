import { useEffect, useState } from 'react'
import { api, ApiError, BASE_URL } from '../api/client'
import { isMissingMeasurementError, isMixedDataSourceError } from '../api/errors'

export type ResourceErrorCode = 'mixed_data_source' | 'missing_measurement' | 'not_found' | null
export interface Resource<T> {
  data: T | null
  loading: boolean
  error: string | null
  errorCode?: ResourceErrorCode
  retry: () => void
}
type ResourceState<T> = Omit<Resource<T>, 'retry'>

const IDLE: ResourceState<never> = { data: null, loading: false, error: null }
const LOADING: ResourceState<never> = { data: null, loading: true, error: null }

export function describeError(error: unknown): string {
  if (error instanceof ApiError) return error.message
  return `Could not load data. Check that the backend is running at ${BASE_URL}, then retry.`
}

export function errorCodeOf(error: unknown): ResourceErrorCode {
  if (isMixedDataSourceError(error)) return 'mixed_data_source'
  if (isMissingMeasurementError(error)) return 'missing_measurement'
  return error instanceof ApiError && error.status === 404 ? 'not_found' : null
}

/** A null path waits: nothing is requested until the caller knows what to ask for. */
export function useApiResource<T>(path: string | null): Resource<T> {
  const [attempt, setAttempt] = useState(0)
  const [state, setState] = useState<ResourceState<T> & { path: string | null }>({
    path,
    ...LOADING,
  })
  useEffect(() => {
    if (path === null) return
    const controller = new AbortController()
    setState({ path, ...LOADING })
    api
      .get<T>(path, { signal: controller.signal })
      .then(data => {
        if (!controller.signal.aborted) setState({ path, data, loading: false, error: null })
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return
        setState({
          path,
          data: null,
          loading: false,
          error: describeError(error),
          errorCode: errorCodeOf(error),
        })
      })
    return () => controller.abort()
  }, [path, attempt])
  const current = path === null ? IDLE : state.path === path ? state : LOADING
  return { ...current, retry: () => setAttempt(value => value + 1) }
}
