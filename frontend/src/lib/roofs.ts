import type { Roof } from '../api/types'
import { ALBEDO_RANGE } from './config'

/** Highest scores first; a roof that no longer fits is skipped, not the rest of the list. */
export function selectWithinBudget(roofs: Roof[], budget: number | null): Roof[] {
  if (budget === null || !Number.isFinite(budget) || budget < 0) return []
  let remaining = budget
  return [...roofs]
    .sort((a, b) => b.priority_score - a.priority_score || a.roof_id.localeCompare(b.roof_id))
    .filter(roof => {
      const cost = roof.estimated_cost_eur
      if (!Number.isFinite(cost) || cost <= 0 || cost > remaining) return false
      remaining -= cost
      return true
    })
}

export function albedoColor(albedo: number): string {
  const { min, max } = ALBEDO_RANGE
  const ratio = Math.max(0, Math.min(1, (albedo - min) / (max - min)))
  const dark = [211, 78, 68],
    light = [53, 118, 196]
  return `rgb(${dark.map((value, index) => Math.round(value + (light[index] - value) * ratio)).join(',')})`
}

/** A circle with the roof's area, drawn when the backend has no footprint for it. */
export function roofRadiusM(areaM2: number): number {
  return Math.sqrt(Math.max(areaM2, 0) / Math.PI)
}
