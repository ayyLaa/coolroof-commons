import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { Roof } from '../api/types'
import { ROOF_PAGE_SIZE } from '../lib/config'
import { describeError, errorCodeOf } from './useApiResource'
import type { Resource } from './useApiResource'

type RoofsState = Omit<Resource<Roof[]>, 'retry'> & { city: string }

function roofsPage(city: string, offset: number): string {
  const query = new URLSearchParams({
    city,
    limit: String(ROOF_PAGE_SIZE),
    offset: String(offset),
    include_geometry: 'true',
  })
  return `/roofs?${query}`
}

/** Pages until a short page: Athens alone has 576 roofs, the backend returns 200 at a time. */
async function fetchAllRoofs(city: string, signal: AbortSignal): Promise<Roof[]> {
  const roofs: Roof[] = []
  for (let offset = 0; ; offset += ROOF_PAGE_SIZE) {
    const page = await api.get<Roof[]>(roofsPage(city, offset), { signal })
    roofs.push(...page)
    if (page.length < ROOF_PAGE_SIZE) return roofs
  }
}

/** Every roof of a city with its footprint; filtering by score happens on the client. */
export function useRoofs(city: string): Resource<Roof[]> {
  const [attempt, setAttempt] = useState(0)
  const [state, setState] = useState<RoofsState>({ city, data: null, loading: true, error: null })
  useEffect(() => {
    const controller = new AbortController()
    setState({ city, data: null, loading: true, error: null })
    fetchAllRoofs(city, controller.signal)
      .then(data => {
        if (!controller.signal.aborted) setState({ city, data, loading: false, error: null })
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return
        setState({
          city,
          data: null,
          loading: false,
          error: describeError(error),
          errorCode: errorCodeOf(error),
        })
      })
    return () => controller.abort()
  }, [city, attempt])
  const { city: loadedCity, ...loaded } = state
  const current = loadedCity === city ? loaded : { data: null, loading: true, error: null }
  return { ...current, retry: () => setAttempt(value => value + 1) }
}
