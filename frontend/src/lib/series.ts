import type { TemperatureSeries } from '../api/types'

export interface SeriesPoint {
  minute: number
  before_c: number | null
  after_c: number | null
}

const MS_PER_MINUTE = 60_000
// Readings come every 30 s; tenths of a minute keep each one on its own point.
const MINUTE_RESOLUTION = 10

function byMinute(readings: TemperatureSeries['before']['readings']): Map<number, number> {
  const start = readings.length ? Date.parse(readings[0].timestamp) : 0
  const minuteOf = (timestamp: string): number =>
    Math.round(((Date.parse(timestamp) - start) / MS_PER_MINUTE) * MINUTE_RESOLUTION) /
    MINUTE_RESOLUTION
  return new Map(readings.map(reading => [minuteOf(reading.timestamp), reading.surface_temp_c]))
}

/**
 * The before and after sessions are weeks apart, so their timestamps never coincide.
 * Both warm up from the moment the probe is placed: pairing by minutes since each
 * session's own start puts the two warm-up curves on one axis.
 */
export function pairSeries(series: TemperatureSeries): SeriesPoint[] {
  const before = byMinute(series.before.readings)
  const after = byMinute(series.after.readings)
  const minutes = [...new Set([...before.keys(), ...after.keys()])].sort((a, b) => a - b)
  return minutes.map(minute => ({
    minute,
    before_c: before.get(minute) ?? null,
    after_c: after.get(minute) ?? null,
  }))
}
