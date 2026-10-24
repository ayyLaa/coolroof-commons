import {
  getContract,
  getVerification,
  getWeather,
  sendMeasurement,
  submitToChain,
  uploadPhoto,
} from '../api/demo'
import type { DemoResult, OracleSubmission } from '../api/demo-types'
import type {
  ContractStatus,
  DataSource,
  MeasurementCreateResponse,
  MeasurementPhase,
  MeasurementReading,
  Verification,
  Weather,
  WeatherSeries,
} from '../api/types'
import type { DemoStep } from './demo'
import { stepPause } from './demo'
import type { DemoScenario } from './demo-scenarios'
import { beforeReadings, demoReadings, plateauC } from './demo-readings'
import { drawRoofPhoto } from './demo-photo'
import { nearestWeather, ANOMALY_EXPLANATIONS } from './verification'
import { measurementDay, number, shorten, temperature } from './format'
import { nativeAmount } from './contracts'
import { DEMO_TIMING } from './config'

interface RunContext {
  readings: MeasurementReading[]
  measurement?: MeasurementCreateResponse
  coverage?: number | null
  weather?: WeatherSeries
  record?: Weather | null
  verification?: Verification
  submission?: OracleSubmission
  contract?: ContractStatus
}
interface StepOutput {
  output: string
  detail?: string
  warning?: boolean
  data_source?: DataSource
}
type Step = () => Promise<StepOutput>
export interface DemoRunOptions {
  signal: AbortSignal
  fast: () => boolean
  onStep: (index: number, value: Partial<DemoStep>) => void
}

function measurementOutput(
  scenario: DemoScenario,
  phase: MeasurementPhase,
  readings: MeasurementReading[],
  measurement: MeasurementCreateResponse,
): StepOutput {
  return {
    output: `${readings.length} readings · plateau ${temperature(plateauC(readings))}`,
    detail: `${phase} measurement ${shorten(measurement.measurement_id)} from ${scenario.device_id}`,
    data_source: measurement.data_source,
  }
}

function measurementSteps(
  scenario: DemoScenario,
  context: RunContext,
  signal: AbortSignal,
): Step[] {
  return [
    async () => {
      const readings = beforeReadings(scenario)
      const before = await sendMeasurement(scenario, 'before', readings, signal)
      return measurementOutput(scenario, 'before', readings, before)
    },
    async () => {
      const { readings } = context
      context.measurement = await sendMeasurement(scenario, scenario.phase, readings, signal)
      return measurementOutput(scenario, scenario.phase, readings, context.measurement)
    },
    async () => {
      if (scenario.coverage_pct === null) {
        context.coverage = null
        return {
          output: 'No photo at the storm recheck',
          detail: 'Coverage is not assessed in a storm.',
        }
      }
      const photo = await drawRoofPhoto(scenario.coverage_pct)
      context.coverage = (
        await uploadPhoto(context.measurement!.measurement_id, photo, signal)
      ).coverage_pct
      return {
        output: `${number(context.coverage, 1)}% of the roof coated`,
        detail: 'OpenCV analysis of a synthetic demo photo.',
      }
    },
    async () => {
      const day = measurementDay(scenario.starts_at)!.start
      context.weather = await getWeather(scenario.roof_id, day, signal)
      context.record = nearestWeather(context.weather, context.readings.at(-1)?.timestamp)
      const record = context.record
      if (!record) return { output: 'No weather recorded for the hour', warning: true }
      return {
        output: `${temperature(record.ambient_c)} · ${number(record.radiation_wm2, 0)} W/m² · wind ${number(record.wind_ms)} m/s`,
        detail: `Nearest of ${context.weather.length} hourly records`,
        data_source: record.data_source,
      }
    },
  ]
}

function verificationSteps(
  scenario: DemoScenario,
  context: RunContext,
  signal: AbortSignal,
): Step[] {
  return [
    async () => {
      context.verification = await getVerification(
        scenario.roof_id,
        context.readings[0].timestamp,
        signal,
      )
      const value = context.verification
      return {
        output: `${temperature(value.normalized_delta_c)} normalized · raw ${temperature(value.measured_delta_c)}`,
        detail: `Status ${value.status.replaceAll('_', ' ')}`,
        data_source: value.data_source,
      }
    },
    async () => {
      const flags = context.verification!.anomaly_flags
      return {
        output: flags.length
          ? `${flags.length} flags · ${flags.join(', ').replaceAll('_', ' ')}`
          : 'Clean · 0 flags',
        detail: flags.map(flag => ANOMALY_EXPLANATIONS[flag] ?? flag).join(' '),
        warning: flags.length > 0,
      }
    },
    async () => {
      const { force_majeure: storm, weather } = context.verification!
      const rain = ` · ${number(weather.precipitation_mm)} mm rain`
      return {
        output: `${storm ? 'YES' : 'No'} · gusts ${number(weather.max_gust_ms)} m/s${rain}`,
        detail: storm
          ? 'The storm makes the reading unreliable; the reserve rules apply.'
          : 'Gusts and rain within limits.',
        warning: storm,
      }
    },
    async () => {
      const value = context.verification!
      return {
        output: `Hash ${shorten(value.evidence_hash)}`,
        detail: `Device signature ${shorten(value.device_signature)}`,
      }
    },
  ]
}

function chainSteps(scenario: DemoScenario, context: RunContext, signal: AbortSignal): Step[] {
  return [
    async () => {
      context.submission = await submitToChain(scenario, signal)
      if (context.submission.status === 'not_submitted')
        return {
          output: 'Not submitted · 0 POL paid',
          detail: context.submission.reason ?? 'Verification not approved.',
          warning: true,
        }
      return {
        output: `Tx ${shorten(context.submission.tx_hash)} · block ${context.submission.block_number}`,
        detail: `Submitted by the oracle for the ${scenario.chain_phase} phase.`,
      }
    },
    async () => {
      context.contract = await getContract(scenario.roof_id, signal)
      const { tranche, status, reason } = context.submission!
      const record = context.contract.tranches.find(item => item.name === tranche)
      const paid = status === 'released' || status === 'force_majeure'
      return {
        output: `${tranche?.replaceAll('_', ' ') ?? 'No tranche'} · ${paid ? `paid ${nativeAmount(record?.amount_wei)}` : 'held, 0 POL paid'}`,
        detail: reason ?? context.verification!.reason,
        warning: !paid,
      }
    },
  ]
}

export async function runDemoScenario(
  scenario: DemoScenario,
  options: DemoRunOptions,
): Promise<DemoResult> {
  const context: RunContext = { readings: demoReadings(scenario) }
  const steps = [
    ...measurementSteps(scenario, context, options.signal),
    ...verificationSteps(scenario, context, options.signal),
    ...chainSteps(scenario, context, options.signal),
  ]
  for (const [index, step] of steps.entries()) {
    options.signal.throwIfAborted()
    options.onStep(index, { status: 'running', output: 'Working…' })
    const value = await step()
    options.signal.throwIfAborted()
    options.onStep(index, {
      ...value,
      detail: value.detail ?? '',
      warning: value.warning ?? false,
      status: 'complete',
    })
    if (index < steps.length - 1 && !options.fast())
      await stepPause(DEMO_TIMING.stepDelayMs, options.signal)
  }
  const decided =
    context.contract!.tranches.find(item => item.name === context.submission!.tranche) ?? null
  return {
    roof_id: scenario.roof_id,
    submission: context.submission!,
    verification: context.verification!,
    tranche: decided,
  }
}
