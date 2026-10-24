import { api, ApiError, BASE_URL, oracle, ORACLE_URL } from './client'
import { parseRound } from '@shared/demo-round'
import type { OracleSubmission } from './demo-types'
import type {
  ContractStatus,
  DemoResetResponse,
  DemoRoundStatus,
  MeasurementCreateResponse,
  MeasurementPhase,
  MeasurementReading,
  PhotoUploadResponse,
  Verification,
  WeatherSeries,
} from './types'
import type { DemoScenario } from '../lib/demo-scenarios'
import { DEMO_TIMING } from '../lib/config'

export class DemoResponseError extends Error {}

// The demo's readings and photo are generated, so they are labelled simulated, the same
// as the seed measurements they are compared with.
const DEMO_DATA_SOURCE = 'simulated'

function signalFor(
  signal: AbortSignal,
  timeout: number = DEMO_TIMING.requestTimeoutMs,
): AbortSignal {
  return AbortSignal.any([signal, AbortSignal.timeout(timeout)])
}

const roofPath = (roofId: string): string => encodeURIComponent(roofId)

export function sendMeasurement(
  scenario: DemoScenario,
  phase: MeasurementPhase,
  readings: MeasurementReading[],
  signal: AbortSignal,
): Promise<MeasurementCreateResponse> {
  return api.post<MeasurementCreateResponse>(
    '/measurements',
    {
      roof_id: scenario.roof_id,
      phase,
      readings,
      device_id: scenario.device_id,
      data_source: DEMO_DATA_SOURCE,
    },
    { signal: signalFor(signal) },
  )
}

export function uploadPhoto(
  measurementId: string,
  photo: Blob,
  signal: AbortSignal,
): Promise<PhotoUploadResponse> {
  const form = new FormData()
  form.append('file', photo, 'roof.png')
  return api.upload<PhotoUploadResponse>(
    `/measurements/${encodeURIComponent(measurementId)}/photo`,
    form,
    { signal: signalFor(signal) },
  )
}

export function getWeather(
  roofId: string,
  day: string,
  signal: AbortSignal,
): Promise<WeatherSeries> {
  const query = new URLSearchParams({ start: day, end: day })
  return api.get<WeatherSeries>(`/weather/${roofPath(roofId)}?${query}`, {
    signal: signalFor(signal),
  })
}

/** The backend verifies the roof's latest measurement; it must be the one just sent. */
export async function getVerification(
  roofId: string,
  measuredAt: string,
  signal: AbortSignal,
): Promise<Verification> {
  const value = await api.get<Verification>(`/verification/${roofPath(roofId)}`, {
    signal: signalFor(signal),
  })
  if (Date.parse(value.measured_at) !== Date.parse(measuredAt)) {
    throw new DemoResponseError(
      'The verification belongs to an earlier measurement. Refusing to show a stale result.',
    )
  }
  return value
}

export function getContract(roofId: string, signal: AbortSignal): Promise<ContractStatus> {
  return api.get<ContractStatus>(`/contracts/${roofPath(roofId)}`, { signal: signalFor(signal) })
}

export async function submitToChain(
  scenario: DemoScenario,
  signal: AbortSignal,
): Promise<OracleSubmission> {
  const result = await oracle.post<OracleSubmission>(
    '/submit',
    { roof_id: scenario.roof_id, phase: scenario.chain_phase },
    { signal: signalFor(signal, DEMO_TIMING.submissionTimeoutMs) },
  )
  if (result.status === 'not_submitted') {
    if (
      result.tx_hash !== null ||
      result.block_number !== null ||
      result.explorer_url !== null ||
      !result.reason
    )
      throw new DemoResponseError('The oracle returned an inconsistent refusal.')
    return result
  }
  if (!result.tx_hash || !/^0x[\da-fA-F]{64}$/.test(result.tx_hash)) {
    throw new DemoResponseError(
      'The oracle did not return a transaction hash. Check the escrow before retrying.',
    )
  }
  return result
}

// Typed by the contract, still checked: the round picks which on-chain project is read.
function roundOf(body: Pick<DemoRoundStatus, 'round'> | null): number {
  try {
    return parseRound(body?.round)
  } catch {
    throw new DemoResponseError('The backend did not report a valid demo round.')
  }
}

/** Resets the backend's demo data, which opens the next demo round; returns its number. */
export async function resetDemo(signal: AbortSignal): Promise<number> {
  return roundOf(
    await api.post<DemoResetResponse>('/demo/reset', {}, { signal: signalFor(signal) }),
  )
}

/** The round the backend mirrors, i.e. which on-chain projects ("ATH-0142#3") to read. */
export async function getDemoRound(signal?: AbortSignal): Promise<number> {
  return roundOf(await api.get<DemoRoundStatus>('/demo/round', { signal }))
}

export function demoErrorMessage(error: unknown, submitting = false): string {
  if (error instanceof DemoResponseError) return error.message
  // Both servers answer errors with a message written for the screen.
  if (error instanceof ApiError) return error.message
  if (error instanceof TypeError) {
    return submitting
      ? `Cannot reach the oracle at ${ORACLE_URL}. Start it with "npm run serve" in oracle/.`
      : `Cannot reach the backend at ${BASE_URL}.`
  }
  if (submitting)
    return 'The submission could not be confirmed. It may have reached the chain; check the escrow before retrying.'
  return error instanceof Error ? error.message : 'The demo step failed.'
}
