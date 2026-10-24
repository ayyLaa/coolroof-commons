import { describe, expect, it } from 'vitest'
import type { Roof } from '../../src/api/types'
import { albedoColor, roofRadiusM, selectWithinBudget } from '../../src/lib/roofs'
import { measurementDay } from '../../src/lib/format'

function roof(id: string, score: number, cost: number): Roof {
  return {
    roof_id: id,
    city: 'Athens',
    roof_class: 'small',
    lat: 37.9,
    lon: 23.7,
    area_m2: 200,
    albedo: 0.2,
    surface_temp_c: 50,
    priority_score: score,
    estimated_cost_eur: cost,
    status: 'candidate',
    data_source: 'measured',
    geometry: null,
  }
}

describe('Budget allocation', () => {
  it('prioritizes scores, skips unaffordable roofs and includes exact-cost matches', () => {
    const roofs = [roof('low', 0.4, 30), roof('high', 0.9, 70), roof('expensive', 0.8, 80)]
    expect(selectWithinBudget(roofs, 100).map(item => item.roof_id)).toEqual(['high', 'low'])
    expect(roofs[0].roof_id).toBe('low')
  })
  it('does not select zero, negative or non-finite costs', () => {
    const roofs = [
      roof('zero', 0.98, 0),
      roof('negative', 0.97, -1),
      roof('infinite', 0.96, Infinity),
    ]
    expect(selectWithinBudget(roofs, 1000)).toEqual([])
  })
  it('handles empty and invalid budgets without choosing roofs', () => {
    for (const budget of [null, 0, -1, NaN, Infinity])
      expect(selectWithinBudget([roof('valid', 0.9, 100)], budget)).toEqual([])
  })
  it('resolves tied scores deterministically', () => {
    expect(selectWithinBudget([roof('B', 0.9, 100), roof('A', 0.9, 100)], 100)[0].roof_id).toBe('A')
  })
})

describe('Map representation', () => {
  it('draws a roof without a footprint as a circle of the same area', () => {
    expect(Math.PI * roofRadiusM(200) ** 2).toBeCloseTo(200)
    expect(roofRadiusM(-5)).toBe(0)
  })
  it('uses red for dark roofs, blue for light roofs, and clamps extremes', () => {
    expect(albedoColor(0)).toBe('rgb(211,78,68)')
    expect(albedoColor(1)).toBe('rgb(53,118,196)')
    expect(albedoColor(-1)).toBe(albedoColor(0))
    expect(albedoColor(2)).toBe(albedoColor(1))
  })
})

describe('Weather range', () => {
  it('asks for the measurement day in UTC', () => {
    expect(measurementDay('2027-01-21T09:00:00Z')).toEqual({
      start: '2027-01-21',
      end: '2027-01-21',
    })
    expect(measurementDay(undefined)).toBeNull()
    expect(measurementDay('not a date')).toBeNull()
  })
})
