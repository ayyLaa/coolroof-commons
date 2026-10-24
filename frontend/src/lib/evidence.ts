import type { SatelliteCase } from '../api/types'

export function significanceLabel(value: {
  significant: boolean | null | undefined
  p_value: number | null | undefined
}): string {
  const p = value.p_value
  const pValue = p != null && Number.isFinite(p) && p >= 0 && p <= 1 ? `p = ${p}` : 'p unavailable'
  if (value.significant === false) return `Not statistically significant (${pValue})`
  if (value.significant === true) return `Statistically significant (${pValue})`
  return `Significance not supplied (${pValue})`
}

/** The instrument family a juror recognises, from the product name the backend reports. */
export function instrumentLabel(instrument: string): string {
  if (instrument.startsWith('Landsat')) return 'Landsat 8/9'
  if (instrument.startsWith('ECOSTRESS')) return 'ECOSTRESS'
  return instrument
}

export type Correction = 'survives' | 'raw_only' | 'none'

/** A raw p < 0.05 that Bonferroni removes is not a finding, and must not look like one. */
export function correctionOf(
  value: Pick<SatelliteCase, 'significant_raw' | 'significant_bonferroni'>,
): Correction {
  if (value.significant_bonferroni) return 'survives'
  return value.significant_raw ? 'raw_only' : 'none'
}

export function formatP(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return 'n/a'
  return value < 0.001 ? '< 0.001' : value.toFixed(3)
}
