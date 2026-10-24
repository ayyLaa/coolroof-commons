import type { MetricsReport } from '../api/types'

export interface NormalizationSpread {
  rawRangeC: number
  normalizedRangeC: number
  factor: number | null
}

/** How much normalisation narrows the spread of the same coating measured on different days. */
export function normalizationSpread(report: MetricsReport): NormalizationSpread {
  const { raw_delta, normalized_delta, spread_reduction_factor } = report.normalization
  return {
    rawRangeC: raw_delta.range_c,
    normalizedRangeC: normalized_delta.range_c,
    factor: spread_reduction_factor,
  }
}

export function sessionCounts(report: MetricsReport): { sessions: number; anomalies: number } {
  const { sessions, anomalies } = report.anomaly_detection
  return { sessions, anomalies }
}
