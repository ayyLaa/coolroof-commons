import { describe, expect, it } from 'vitest'
import type { MetricsReport, TemperatureSeries, Weather } from '../../src/api/types'
import { pairSeries } from '../../src/lib/series'
import { nearestWeather, splitReason } from '../../src/lib/verification'
import { correctionOf, formatP, instrumentLabel } from '../../src/lib/evidence'
import { normalizationSpread, sessionCounts } from '../../src/lib/metrics'

function readings(start: string, temps: number[]): TemperatureSeries['before']['readings'] {
  return temps.map((surface_temp_c, index) => ({
    timestamp: new Date(Date.parse(start) + index * 30_000).toISOString(),
    surface_temp_c,
    data_source: 'simulated' as const,
  }))
}

describe('Temperature series', () => {
  it('pairs sessions weeks apart by time since each probe was placed', () => {
    const series = {
      roof_id: 'ATH-0142',
      data_source: 'simulated',
      model: 'physical',
      weather_source: 'Open-Meteo',
      before: {
        start: '2026-06-15T10:00:00Z',
        albedo: 0.12,
        readings: readings('2026-06-15T10:00:00Z', [60, 61, 62]),
      },
      after: {
        start: '2026-07-15T10:00:00Z',
        albedo: 0.7,
        readings: readings('2026-07-15T10:00:00Z', [45, 46]),
      },
    } satisfies TemperatureSeries
    expect(pairSeries(series)).toEqual([
      { minute: 0, before_c: 60, after_c: 45 },
      { minute: 0.5, before_c: 61, after_c: 46 },
      { minute: 1, before_c: 62, after_c: null },
    ])
  })
})

describe('Weather at measurement', () => {
  const hour = (time: string, source: Weather['data_source']): Weather => ({
    timestamp: time,
    ambient_c: 30,
    radiation_wm2: 800,
    wind_ms: 3,
    max_gust_ms: 6,
    precipitation_mm: 0,
    data_source: source,
  })
  it('takes the hourly record nearest the measurement', () => {
    const rows = [
      hour('2026-07-15T07:00:00Z', 'third_party'),
      hour('2026-07-15T08:00:00Z', 'simulated'),
    ]
    expect(nearestWeather(rows, '2026-07-15T08:10:00Z')?.data_source).toBe('simulated')
    expect(nearestWeather(rows, null)).toBeNull()
    expect(nearestWeather([], '2026-07-15T08:00:00Z')).toBeNull()
  })
})

describe('Verification reason', () => {
  it('separates the winter-penalty note from the decision', () => {
    const { decision, note } = splitReason(
      'Meets the -6.0C threshold. Note: this climate has a real heating season.',
    )
    expect(decision).toBe('Meets the -6.0C threshold.')
    expect(note).toBe('this climate has a real heating season.')
    expect(splitReason('Meets the threshold.').note).toBeNull()
  })
})

describe('Satellite evidence', () => {
  it('never presents a raw-only result as surviving correction', () => {
    expect(correctionOf({ significant_raw: true, significant_bonferroni: false })).toBe('raw_only')
    expect(correctionOf({ significant_raw: true, significant_bonferroni: true })).toBe('survives')
    expect(correctionOf({ significant_raw: false, significant_bonferroni: false })).toBe('none')
  })
  it('names the instrument family', () => {
    expect(instrumentLabel('Landsat 8/9 C2L2 ST_B10')).toBe('Landsat 8/9')
    expect(instrumentLabel('ECOSTRESS L2T LSTE V2')).toBe('ECOSTRESS')
  })
  it('formats p-values without overstating precision', () => {
    expect(formatP(0.0234)).toBe('0.023')
    expect(formatP(0.00001)).toBe('< 0.001')
    expect(formatP(undefined)).toBe('n/a')
  })
})

describe('Method metrics', () => {
  it('reads the normalization spread and session counts from the typed report', () => {
    const report = metricsReport()
    expect(normalizationSpread(report)).toEqual({
      rawRangeC: 19.1,
      normalizedRangeC: 3.87,
      factor: 3.2,
    })
    expect(sessionCounts(report)).toEqual({ sessions: 387, anomalies: 181 })
  })
  it('passes on a missing reduction factor instead of inventing one', () => {
    const report = metricsReport()
    report.normalization.spread_reduction_factor = null
    expect(normalizationSpread(report).factor).toBeNull()
  })
})

function detector() {
  return { true_positives: 1, false_positives: 0, false_negatives: 0, precision: 1, recall: 1 }
}

function spread(mean_c: number, range_c: number) {
  return { mean_c, std_c: 1, min_c: mean_c - range_c / 2, max_c: mean_c + range_c / 2, range_c }
}

function metricsReport(): MetricsReport {
  return {
    data_source: 'simulated',
    generated_at: '2026-10-21T12:00:00Z',
    anomaly_detection: {
      data_source: 'simulated',
      sessions: 387,
      anomalies: 181,
      rules: detector(),
      isolation_forest: detector(),
      combined: detector(),
      detection_rate_by_kind: { frozen_sensor: { n: 20, rules: 1, isolation_forest: 0.1 } },
    },
    normalization: {
      data_source: 'simulated',
      weather_source: 'open-meteo (real hourly weather)',
      weather_roof_id: 'ATH-1000',
      albedo_before: 0.271,
      albedo_after: 0.75,
      before_measured_at: '2026-07-01T13:00:00+03:00',
      true_delta_at_standard_c: -21.1,
      raw_delta: spread(-18.18, 19.1),
      normalized_delta: spread(-20.01, 3.87),
      spread_reduction_factor: 3.2,
      scenarios: [],
    },
  }
}
