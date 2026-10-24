import type { MeasurementPhase } from '../api/types'

export type Curve =
  { kind: 'warm-up'; start_c: number; plateau_c: number } | { kind: 'storm'; center_c: number }

/** The baseline visit before coating, sent first so each run measures its own delta. */
export interface BeforeVisit {
  // Half a minute after the seed's before measurement, so the seed's weather for that
  // hour applies and this upload is the latest baseline the backend compares against.
  starts_at: string
  curve: Curve
}

export interface DemoScenario {
  id: string
  roof_id: string
  title: string
  description: string
  tone: string
  before: BeforeVisit
  /** The follow-up measurement, uploaded after the baseline. */
  phase: MeasurementPhase
  /** The tranche the oracle submits for. */
  chain_phase: 'quality' | 'durability'
  device_id: string
  // Half a minute after the seed's own measurement, inside the same weather hour: the
  // backend verifies the latest measurement against the seed's weather for that hour,
  // which for ATH-0355 is the storm.
  starts_at: string
  curve: Curve
  /** Share of the roof painted in the photo; null when the recheck has no photo. */
  coverage_pct: number | null
}

export const DEMO_SCENARIOS: DemoScenario[] = [
  {
    id: 'success',
    roof_id: 'ATH-0142',
    title: 'Successful intervention',
    tone: 'success',
    description: 'Cooling and coverage pass. The quality tranche is released.',
    before: {
      starts_at: '2026-06-01T07:00:30Z',
      curve: { kind: 'warm-up', start_c: 58.3, plateau_c: 61.6 },
    },
    phase: 'after',
    chain_phase: 'quality',
    device_id: 'DEV-0391',
    starts_at: '2026-07-15T08:00:30Z',
    curve: { kind: 'warm-up', start_c: 46.1, plateau_c: 48.4 },
    coverage_pct: 94.5,
  },
  {
    id: 'poor_coating',
    roof_id: 'ATH-0287',
    title: 'Poor coating',
    tone: 'warning',
    description: 'Weak cooling and low coverage. Payment stays in escrow.',
    before: {
      starts_at: '2026-06-05T07:00:30Z',
      curve: { kind: 'warm-up', start_c: 59.0, plateau_c: 61.0 },
    },
    phase: 'after',
    chain_phase: 'quality',
    device_id: 'DEV-0214',
    starts_at: '2026-07-20T08:00:30Z',
    curve: { kind: 'warm-up', start_c: 57.2, plateau_c: 58.1 },
    coverage_pct: 41,
  },
  {
    id: 'storm',
    roof_id: 'ATH-0355',
    title: 'Storm scenario',
    tone: 'storm',
    description: 'Quality was already paid. A storm at the recheck releases the reserve.',
    before: {
      starts_at: '2026-06-10T07:00:30Z',
      curve: { kind: 'warm-up', start_c: 57.2, plateau_c: 59.8 },
    },
    phase: 'durability',
    chain_phase: 'durability',
    device_id: 'DEV-0502',
    starts_at: '2027-01-21T09:00:30Z',
    curve: { kind: 'storm', center_c: 50 },
    coverage_pct: null,
  },
]
