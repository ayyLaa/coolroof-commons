import type { MeasurementPhase, MeasurementReading } from '../api/types'
import type { Curve, DemoScenario } from './demo-scenarios'

// Sixteen one-minute readings: what the backend needs (at least ten, no gap over five
// minutes) to find the temperature plateau.
const READING_COUNT = 16
const STEP_MS = 60_000
const WARMUP_RATE = 0.35
const SENSOR_NOISE_C = 0.25
const STORM_NOISE_C = 2.5
const DECIMALS = 100

/** Deterministic noise, so a scenario uploads the same readings every run. */
export function seededNoise(seed: string): () => number {
  let state =
    [...seed].reduce((hash, char) => Math.imul(hash ^ char.charCodeAt(0), 16777619), 2166136261) >>>
    0
  return () => {
    state = (state + 0x6d2b79f5) >>> 0
    let value = Math.imul(state ^ (state >>> 15), 1 | state)
    value ^= value + Math.imul(value ^ (value >>> 7), 61 | value)
    return (((value ^ (value >>> 14)) >>> 0) / 4294967296) * 2 - 1
  }
}

function temperatureAt(curve: Curve, minute: number, noise: () => number): number {
  if (curve.kind === 'storm') return curve.center_c + noise() * STORM_NOISE_C
  const progress = 1 - Math.exp(-WARMUP_RATE * minute)
  return curve.start_c + (curve.plateau_c - curve.start_c) * progress + noise() * SENSOR_NOISE_C
}

function visitReadings(
  roofId: string,
  phase: MeasurementPhase,
  startsAt: string,
  curve: Curve,
): MeasurementReading[] {
  const start = Date.parse(startsAt)
  const noise = seededNoise(`${roofId}-${phase}-demo`)
  return Array.from({ length: READING_COUNT }, (_, minute) => ({
    timestamp: new Date(start + minute * STEP_MS).toISOString(),
    surface_temp_c: Math.round(temperatureAt(curve, minute, noise) * DECIMALS) / DECIMALS,
  }))
}

/** The follow-up visit: after coating, or the storm's durability recheck. */
export function demoReadings(scenario: DemoScenario): MeasurementReading[] {
  return visitReadings(scenario.roof_id, scenario.phase, scenario.starts_at, scenario.curve)
}

export function beforeReadings(scenario: DemoScenario): MeasurementReading[] {
  const { starts_at, curve } = scenario.before
  return visitReadings(scenario.roof_id, 'before', starts_at, curve)
}

/** The backend's plateau: the mean of the last three readings. */
export function plateauC(readings: MeasurementReading[]): number {
  const tail = readings.slice(-3)
  return tail.reduce((sum, reading) => sum + reading.surface_temp_c, 0) / tail.length
}
