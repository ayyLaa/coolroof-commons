import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { runDemoScenario } from '../../src/lib/demo-runner'
import { DEMO_SCENARIOS, demoReducer, emptyDemoState, stepPause } from '../../src/lib/demo'
import { beforeReadings, demoReadings, plateauC } from '../../src/lib/demo-readings'
import {
  getContract,
  getVerification,
  getWeather,
  sendMeasurement,
  submitToChain,
  uploadPhoto,
} from '../../src/api/demo'
import type { DemoResult, OracleSubmission } from '../../src/api/demo-types'
import type { ContractStatus, Verification, Weather } from '../../src/api/types'

vi.mock('../../src/api/demo', () => ({
  sendMeasurement: vi.fn(),
  uploadPhoto: vi.fn(),
  getWeather: vi.fn(),
  getVerification: vi.fn(),
  getContract: vi.fn(),
  submitToChain: vi.fn(),
}))
// No canvas in the test environment; the photo itself is checked against the backend.
vi.mock('../../src/lib/demo-photo', () => ({ drawRoofPhoto: vi.fn(async () => new Blob()) }))

const [SUCCESS, , STORM] = DEMO_SCENARIOS
const TX = `0x${'ab'.repeat(32)}`
const verification: Verification = {
  measurement_id: '11111111-1111-4111-8111-111111111111',
  measurement_phase: 'after',
  roof_id: 'ATH-0142',
  status: 'approved',
  measured_delta_c: -13.1,
  normalized_delta_c: -17.1,
  coverage_pct: 94.5,
  anomaly_flags: [],
  force_majeure: false,
  weather: {
    ambient_c: 34,
    radiation_wm2: 850,
    wind_ms: 3,
    max_gust_ms: 6,
    precipitation_mm: 0,
    window_start: SUCCESS.starts_at,
    window_end: '2026-07-15T09:00:00Z',
  },
  evidence_hash: TX,
  device_signature: `0x${'13'.repeat(65)}`,
  measured_at: SUCCESS.starts_at,
  reason: 'Meets the -8.0C threshold.',
  data_source: 'simulated',
}
const weather: Weather = {
  timestamp: '2026-07-15T08:00:00Z',
  ambient_c: 34,
  radiation_wm2: 850,
  wind_ms: 3,
  max_gust_ms: 6,
  precipitation_mm: 0,
  data_source: 'simulated',
}
const submission: OracleSubmission = {
  tx_hash: TX,
  status: 'released',
  tranche: 'QUALITY',
  reason: null,
  block_number: 7,
  explorer_url: `https://amoy.polygonscan.com/tx/${TX}`,
}
const contract = {
  tranches: [
    {
      name: 'QUALITY',
      pct: 60,
      status: 'released',
      amount_wei: '600000000000000000',
      tx_hash: TX,
      released_at: null,
    },
  ],
} as ContractStatus

beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(sendMeasurement).mockResolvedValue({
    measurement_id: 'm1',
    normalized_delta_c: -17.1,
    anomaly_flags: [],
    data_source: 'simulated',
  })
  vi.mocked(uploadPhoto).mockResolvedValue({
    coverage_pct: 94.5,
    mask_preview_url: 'http://x/mask.png',
  })
  vi.mocked(getWeather).mockResolvedValue([weather])
  vi.mocked(getVerification).mockResolvedValue(verification)
  vi.mocked(submitToChain).mockResolvedValue(submission)
  vi.mocked(getContract).mockResolvedValue(contract)
})
afterEach(() => vi.useRealTimers())

const run = (fast = true, onStep = vi.fn()) =>
  runDemoScenario(SUCCESS, { signal: new AbortController().signal, fast: () => fast, onStep })

describe('Demo orchestration', () => {
  it('completes a refused scenario without inventing a transaction', async () => {
    vi.mocked(getVerification).mockResolvedValue({ ...verification, status: 'flagged' })
    vi.mocked(submitToChain).mockResolvedValue({
      status: 'not_submitted',
      tx_hash: null,
      block_number: null,
      explorer_url: null,
      tranche: 'QUALITY',
      reason: 'Not submitted: status is flagged.',
    })
    const onStep = vi.fn()
    const result = await run(true, onStep)
    expect(result.submission.tx_hash).toBeNull()
    expect(onStep).toHaveBeenCalledWith(
      8,
      expect.objectContaining({ output: 'Not submitted · 0 POL paid', warning: true }),
    )
    expect(onStep).toHaveBeenCalledWith(
      9,
      expect.objectContaining({ output: 'QUALITY · held, 0 POL paid' }),
    )
  })
  it('completes all ten steps with numbers and returns the paid tranche', async () => {
    const onStep = vi.fn()
    const result: DemoResult = await run(true, onStep)
    const outputs = onStep.mock.calls
      .filter(([, value]) => value.status === 'complete')
      .map(([, value]) => value.output)
    expect(outputs).toHaveLength(10)
    expect(outputs[2]).toBe('94.5% of the roof coated')
    expect(outputs[4]).toBe('-17.1 °C normalized · raw -13.1 °C')
    expect(outputs[9]).toBe('QUALITY · paid 0.6 POL')
    expect(result.tranche?.amount_wei).toBe('600000000000000000')
    expect(vi.mocked(sendMeasurement).mock.calls.map(([, phase]) => phase)).toEqual([
      'before',
      'after',
    ])
    expect(sendMeasurement).toHaveBeenNthCalledWith(
      1,
      SUCCESS,
      'before',
      beforeReadings(SUCCESS),
      expect.any(AbortSignal),
    )
  })
  it('skips the photo at the storm recheck and reports the gust, not the wind', async () => {
    vi.mocked(getVerification).mockResolvedValue({
      ...verification,
      force_majeure: true,
      weather: {
        ...verification.weather,
        ambient_c: 19,
        radiation_wm2: 150,
        wind_ms: 14,
        max_gust_ms: 24,
        precipitation_mm: 68,
      },
    })
    vi.mocked(getWeather).mockResolvedValue([
      { ...weather, timestamp: '2027-01-21T09:00:00Z', precipitation_mm: 68 },
    ])
    const onStep = vi.fn()
    await runDemoScenario(STORM, { signal: new AbortController().signal, fast: () => true, onStep })
    expect(uploadPhoto).not.toHaveBeenCalled()
    expect(onStep).toHaveBeenCalledWith(
      6,
      expect.objectContaining({ output: 'YES · gusts 24 m/s · 68 mm rain', warning: true }),
    )
    expect(submitToChain).toHaveBeenCalledWith(STORM, expect.any(AbortSignal))
  })
  it('waits 600 ms between steps in reading mode', async () => {
    vi.useFakeTimers()
    const promise = run(false)
    await vi.advanceTimersByTimeAsync(600 * 2 - 1)
    expect(uploadPhoto).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(1)
    expect(uploadPhoto).toHaveBeenCalledOnce()
    await vi.advanceTimersByTimeAsync(600 * 8)
    await expect(promise).resolves.toMatchObject({ roof_id: 'ATH-0142' })
  })
  it('stops at a failed step without a chain submission or a made-up result', async () => {
    vi.mocked(getVerification).mockRejectedValue(new Error('Verification offline'))
    await expect(run()).rejects.toThrow('Verification offline')
    expect(submitToChain).not.toHaveBeenCalled()
  })
  it('cancels a pending pause', async () => {
    const abort = new AbortController()
    const pause = stepPause(600, abort.signal)
    abort.abort()
    await expect(pause).rejects.toMatchObject({ name: 'AbortError' })
  })
})

describe('Demo readings', () => {
  it('uploads sixteen one-minute readings from the scenario start, the same every run', () => {
    const readings = demoReadings(SUCCESS)
    expect(readings).toHaveLength(16)
    expect(readings[0].timestamp).toBe(new Date(SUCCESS.starts_at).toISOString())
    expect(Date.parse(readings[1].timestamp) - Date.parse(readings[0].timestamp)).toBe(60_000)
    expect(demoReadings(SUCCESS)).toEqual(readings)
    expect(plateauC(readings)).toBeCloseTo(48.4, 0)
  })
  it('sends its own baseline, half a minute after the seed one', () => {
    for (const scenario of DEMO_SCENARIOS) {
      const before = beforeReadings(scenario)
      expect(before).toHaveLength(16)
      expect(before[0].timestamp).toBe(new Date(scenario.before.starts_at).toISOString())
      expect(Date.parse(before[0].timestamp)).toBeLessThan(Date.parse(scenario.starts_at))
    }
    expect(plateauC(beforeReadings(SUCCESS))).toBeCloseTo(61.6, 0)
  })
  it('never repeats a value five times, which the backend flags as a frozen sensor', () => {
    for (const readings of DEMO_SCENARIOS.flatMap(s => [demoReadings(s), beforeReadings(s)])) {
      const values = readings.map(reading => reading.surface_temp_c)
      expect(
        values.some(
          (value, index) => values.slice(index, index + 5).filter(v => v === value).length === 5,
        ),
      ).toBe(false)
    }
  })
})

describe('Demo state', () => {
  const result: DemoResult = {
    roof_id: 'ATH-0142',
    submission,
    verification,
    tranche: contract.tranches[0],
  }
  it('only clears a completed run after reset is acknowledged', () => {
    let state = demoReducer(emptyDemoState(), { type: 'begin', scenario: SUCCESS })
    state = demoReducer(state, { type: 'finish', result })
    state = demoReducer(state, { type: 'reset-start' })
    expect(state.result).toEqual(result)
    state = demoReducer(state, { type: 'reset-fail', message: 'Offline' })
    expect(state.completedRoofs).toEqual(['ATH-0142'])
    state = demoReducer(state, { type: 'reset-done', round: 4 })
    expect(state).toEqual({ ...emptyDemoState(), unfundedRound: 4 })
  })
  it('keeps the unfunded-round warning while a scenario runs after a reset', () => {
    let state = demoReducer(emptyDemoState(), { type: 'reset-done', round: 4 })
    state = demoReducer(state, { type: 'begin', scenario: SUCCESS })
    expect(state.unfundedRound).toBe(4)
  })
  it('marks only the active step as failed and preserves completed steps', () => {
    let state = demoReducer(emptyDemoState(), { type: 'begin', scenario: SUCCESS })
    state = demoReducer(state, { type: 'step', index: 0, value: { status: 'complete' } })
    state = demoReducer(state, { type: 'step', index: 1, value: { status: 'running' } })
    state = demoReducer(state, { type: 'fail', message: 'Offline' })
    expect(state.steps.map(step => step.status).slice(0, 3)).toEqual([
      'complete',
      'error',
      'pending',
    ])
  })
})
