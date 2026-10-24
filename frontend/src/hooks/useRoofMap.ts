import { useState } from 'react'
import type { Dispatch, SetStateAction } from 'react'
import { useDebouncedValue } from '@mantine/hooks'
import type { Roof } from '../api/types'
import type { Resource } from './useApiResource'
import { useRoofs } from './useRoofs'
import { selectWithinBudget } from '../lib/roofs'
import { DEFAULT_BUDGET_EUR, PRIORITY_SCORE } from '../lib/config'
import { useCitySelection } from './useCitySelection'
import { useSelectedRoof } from './useSelectedRoof'

const SCORE_DEBOUNCE_MS = 200

interface RoofMapState extends Resource<Roof[]>, ReturnType<typeof useCitySelection> {
  roofs: Roof[]
  totalRoofs: number
  chosen: Roof[]
  selected: Roof | null
  minScore: number
  setMinScore: Dispatch<SetStateAction<number>>
  budget: number | null
  setBudget: Dispatch<SetStateAction<number | null>>
  setSelectedId: (id: string | null) => void
}

export function useRoofMap(): RoofMapState {
  const citySelection = useCitySelection()
  const [minScore, setMinScore] = useState<number>(PRIORITY_SCORE.min)
  const [debouncedScore] = useDebouncedValue(minScore, SCORE_DEBOUNCE_MS)
  const [budget, setBudget] = useState<number | null>(DEFAULT_BUDGET_EUR)
  const [selectedId, setSelected] = useState<string | null>(null)
  const { setRoofId } = useSelectedRoof()
  const setSelectedId = (id: string | null): void => {
    setSelected(id)
    if (id) setRoofId(id)
  }
  const resource = useRoofs(citySelection.city.name)
  const allRoofs = resource.data ?? []
  const roofs = allRoofs.filter(roof => roof.priority_score >= debouncedScore)
  const chosen = selectWithinBudget(roofs, budget)
  const selected = roofs.find(roof => roof.roof_id === selectedId) ?? null
  const setCity = (id: string): void => {
    setSelectedId(null)
    citySelection.setCity(id)
  }
  return {
    ...citySelection,
    ...resource,
    setCity,
    roofs,
    totalRoofs: allRoofs.length,
    chosen,
    selected,
    minScore,
    setMinScore,
    budget,
    setBudget,
    setSelectedId,
  }
}
