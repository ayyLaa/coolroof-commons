import type {
  ClimateComparison,
  ContractStatus,
  MetricsReport,
  RoofDetail,
  SatelliteEvidence,
  TemperatureSeries,
  Verification,
  WeatherSeries,
} from '../api/types'
import { useEffect, useState } from 'react'
import { getDemoRound } from '../api/demo'
import { describeError, useApiResource } from './useApiResource'
import type { Resource } from './useApiResource'
import type { RoundLookup } from './useChainComparison'

// One hook per backend endpoint, typed by the generated schema. Components call these,
// never fetch. The list of roofs is paged and lives in useRoofs.

export interface DayRange {
  start: string
  end: string
}

const roofPath = (roofId: string): string => encodeURIComponent(roofId)

/** The demo round the backend mirrors; retry reads it again after scripts/demo-round.sh. */
export function useDemoRound(): RoundLookup & { retry: () => void } {
  const [attempt, setAttempt] = useState(0)
  const [lookup, setLookup] = useState<RoundLookup>({ round: null, error: null })
  useEffect(() => {
    const controller = new AbortController()
    setLookup({ round: null, error: null })
    getDemoRound(controller.signal)
      .then(round => setLookup({ round, error: null }))
      .catch((error: unknown) => {
        if (!controller.signal.aborted)
          setLookup({ round: null, error: `Demo round unavailable. ${describeError(error)}` })
      })
    return () => controller.abort()
  }, [attempt])
  return { ...lookup, retry: () => setAttempt(value => value + 1) }
}

export function useRoof(roofId: string): Resource<RoofDetail> {
  return useApiResource<RoofDetail>(`/roofs/${roofPath(roofId)}`)
}

export function useSeries(roofId: string): Resource<TemperatureSeries> {
  return useApiResource<TemperatureSeries>(`/roofs/${roofPath(roofId)}/series`)
}

export function useVerification(roofId: string): Resource<Verification> {
  return useApiResource<Verification>(`/verification/${roofPath(roofId)}`)
}

/** start and end are required by the backend; with no range yet nothing is requested. */
export function useWeather(roofId: string, range: DayRange | null): Resource<WeatherSeries> {
  const query = range && new URLSearchParams({ start: range.start, end: range.end })
  return useApiResource<WeatherSeries>(query ? `/weather/${roofPath(roofId)}?${query}` : null)
}

export function useContract(roofId: string): Resource<ContractStatus> {
  return useApiResource<ContractStatus>(`/contracts/${roofPath(roofId)}`)
}

export function useSatelliteEvidence(): Resource<SatelliteEvidence> {
  return useApiResource<SatelliteEvidence>('/evidence/satellite')
}

export function useClimateComparison(): Resource<ClimateComparison> {
  return useApiResource<ClimateComparison>('/evidence/climate-comparison')
}

export function useMetrics(): Resource<MetricsReport> {
  return useApiResource<MetricsReport>('/metrics')
}
