import type { Weather } from '../api/types'

// Every flag the backend can emit (ml/anomaly.py and services/decision.py), in plain words.
export const ANOMALY_EXPLANATIONS: Record<string, string> = {
  repeated_value:
    'The sensor reported the same temperature five or more times in a row, as a frozen probe would.',
  impossible_jump:
    'Temperature jumped more than 10 °C between two readings, faster than a roof can change.',
  shadow_suspect:
    'A large drop under weak sunlight: more likely a probe in shade than a working coating.',
  missing_weather:
    'No weather record exists for the measurement, so the result cannot be normalized.',
  too_few_readings:
    'Fewer than ten readings were uploaded, too few to find the temperature plateau.',
  timestamp_gap: 'More than five minutes pass between two readings, so the session is incomplete.',
  replay: 'The temperature sequence matches an earlier upload from this device.',
  statistical_outlier: 'The session does not look like normal measurements (Isolation Forest).',
  extreme_wind_event: 'Wind gusts exceeded the force majeure limit during the measurement.',
  heavy_precipitation: 'Rainfall exceeded the force majeure limit during the measurement.',
  normalized_delta_below_threshold:
    'The normalized cooling does not reach the threshold for this city.',
  coverage_below_threshold: 'Too little of the roof is coated to meet the coverage requirement.',
}
export const UNKNOWN_FLAG =
  'The backend flagged this measurement for review without a known explanation.'

const NOTE_MARKER = ' Note: '

/** The backend appends the winter-penalty note to the reason; it never changes the status. */
export function splitReason(reason: string): { decision: string; note: string | null } {
  const at = reason.indexOf(NOTE_MARKER)
  if (at < 0) return { decision: reason, note: null }
  return { decision: reason.slice(0, at), note: reason.slice(at + NOTE_MARKER.length) }
}

/** The hourly record closest to the measurement, which is what normalization used. */
export function nearestWeather(
  rows: Weather[],
  measuredAt: string | null | undefined,
): Weather | null {
  const target = measuredAt ? Date.parse(measuredAt) : NaN
  if (!rows.length || Number.isNaN(target)) return null
  const distance = (row: Weather): number => Math.abs(Date.parse(row.timestamp) - target)
  return rows.reduce((nearest, row) => (distance(row) < distance(nearest) ? row : nearest))
}
